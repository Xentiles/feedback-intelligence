"""Allow-listed privacy telemetry that cannot contain feedback bodies."""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.util.types import AttributeValue

from feedback_intelligence_worker.privacy.models import ModelSafeFeedbackState

TRACE_ATTRIBUTE_ALLOW_LIST = frozenset(
    {
        "attempt.count",
        "decision.engine",
        "decision.id",
        "destination",
        "error.type",
        "event.id",
        "feedback.id",
        "ingestion.outcome",
        "job.id",
        "latency.ms",
        "model.version",
        "policy.disposition",
        "privacy.status",
        "projection.outcome",
        "redaction.count",
        "schema.version",
        "source.type",
    }
)

METRIC_ATTRIBUTE_ALLOW_LIST = frozenset(
    {
        "decision.engine",
        "destination",
        "error.type",
        "ingestion.outcome",
        "policy.disposition",
        "projection.outcome",
        "schema.version",
        "source.type",
    }
)


def redaction_event(state: ModelSafeFeedbackState) -> dict[str, Any]:
    """Build the complete allowed event payload for a successful redaction."""
    return {
        "event.name": "feedback.redact",
        "feedback.id": state.feedback_id,
        "source.provider": state.source_provider_id,
        "privacy.status": state.privacy_status,
        "redaction.count": state.redactions.total,
        "redaction.kinds": sorted(kind.value for kind in state.redactions.counts),
        "input.sha256": state.redacted_text_sha256,
    }


def safe_trace_attributes(attributes: Mapping[str, object]) -> dict[str, AttributeValue]:
    """Return only explicitly permitted trace fields."""
    return _safe_attributes(attributes, TRACE_ATTRIBUTE_ALLOW_LIST)


def safe_metric_attributes(attributes: Mapping[str, object]) -> dict[str, AttributeValue]:
    """Return low-cardinality metric fields from the explicit allow-list."""
    return _safe_attributes(attributes, METRIC_ATTRIBUTE_ALLOW_LIST)


def _safe_attributes(
    attributes: Mapping[str, object], allow_list: frozenset[str]
) -> dict[str, AttributeValue]:
    safe: dict[str, AttributeValue] = {}
    for key, value in attributes.items():
        if key in allow_list and isinstance(value, str | bool | int | float):
            safe[key] = value
    return safe


class WorkerTelemetry:
    """OTLP traces and metrics with a content-free attribute boundary."""

    def __init__(self, *, enabled: bool, endpoint: str, service_name: str) -> None:
        self.enabled = enabled
        self._tracer_provider: TracerProvider | None = None
        self._meter_provider: MeterProvider | None = None
        self._tracer = None
        self._processed = None
        self._decision_errors = None
        self._decision_latency = None
        self._projection = None
        if not enabled:
            return

        resource = Resource.create({SERVICE_NAME: service_name})
        insecure = endpoint.startswith("http://")
        self._tracer_provider = TracerProvider(resource=resource)
        self._tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=endpoint, insecure=insecure, timeout=3),
                export_timeout_millis=3_000,
            )
        )
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint, insecure=insecure, timeout=3),
            export_interval_millis=10_000,
            export_timeout_millis=3_000,
        )
        self._meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        self._tracer = self._tracer_provider.get_tracer("feedback_intelligence.worker")
        meter = self._meter_provider.get_meter("feedback_intelligence.worker")
        self._processed = meter.create_counter("feedback_processed_total")
        self._decision_errors = meter.create_counter("decision_errors_total")
        self._decision_latency = meter.create_histogram("decision_latency_ms", unit="ms")
        self._projection = meter.create_counter("analytics_projection_total")

    @classmethod
    def from_environment(cls) -> WorkerTelemetry:
        return cls(
            enabled=os.getenv("OTEL_ENABLED", "false").casefold() == "true",
            endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
            service_name=os.getenv("OTEL_SERVICE_NAME", "feedback-intelligence-decision-worker"),
        )

    @contextmanager
    def span(
        self,
        name: str,
        attributes: Mapping[str, object],
        *,
        parent: otel_context.Context | None = None,
    ) -> Iterator[Span | None]:
        if not self.enabled or self._tracer is None:
            yield None
            return
        with self._tracer.start_as_current_span(
            name,
            context=parent,
            attributes=safe_trace_attributes(attributes),
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield span
            except Exception as error:
                self.mark_error(span, error)
                raise

    @staticmethod
    def parent_context(traceparent: str | None, tracestate: str | None) -> otel_context.Context:
        carrier = {}
        if traceparent:
            carrier["traceparent"] = traceparent
        if tracestate:
            carrier["tracestate"] = tracestate
        return TraceContextTextMapPropagator().extract(carrier=carrier)

    @staticmethod
    def current_context_carrier() -> tuple[str | None, str | None]:
        carrier: dict[str, str] = {}
        TraceContextTextMapPropagator().inject(carrier=carrier)
        return carrier.get("traceparent"), carrier.get("tracestate")

    @staticmethod
    def mark_error(span: Span | None, error: Exception) -> None:
        if span is not None:
            span.set_attribute("error.type", type(error).__name__)
            span.set_status(Status(StatusCode.ERROR))

    def record_decision(self, *, engine: str, latency_ms: int) -> None:
        if self._processed is None or self._decision_latency is None:
            return
        attributes = safe_metric_attributes({"decision.engine": engine})
        self._processed.add(1, attributes)
        self._decision_latency.record(latency_ms, attributes)

    def record_decision_error(self, *, engine: str, error: Exception) -> None:
        if self._decision_errors is None:
            return
        attributes = safe_metric_attributes(
            {"decision.engine": engine, "error.type": type(error).__name__}
        )
        self._decision_errors.add(1, attributes)

    def record_projection(self, *, destination: str, outcome: str) -> None:
        if self._projection is None:
            return
        attributes = safe_metric_attributes(
            {"destination": destination, "projection.outcome": outcome}
        )
        self._projection.add(1, attributes)

    def shutdown(self) -> None:
        if self._meter_provider is not None:
            self._meter_provider.shutdown()
        if self._tracer_provider is not None:
            self._tracer_provider.shutdown()
