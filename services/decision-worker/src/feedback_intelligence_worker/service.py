"""Continuous job and projection service over PostgreSQL leases."""

from __future__ import annotations

import json
import os
import signal
import socket
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from types import FrameType
from typing import Any, Protocol

from feedback_intelligence_worker.data.config import find_repository_root
from feedback_intelligence_worker.data.models import FeedbackRecord
from feedback_intelligence_worker.decision.engine import DecisionEngine
from feedback_intelligence_worker.decision.envelope import build_decision_envelope
from feedback_intelligence_worker.decision.registry import create_decision_engine
from feedback_intelligence_worker.decision.schema import DecisionSchema, load_decision_schema
from feedback_intelligence_worker.privacy import PrivacyBoundary
from feedback_intelligence_worker.privacy.telemetry import WorkerTelemetry
from feedback_intelligence_worker.storage.clickhouse import ClickHouseClient
from feedback_intelligence_worker.storage.events import build_signal_projection_event
from feedback_intelligence_worker.storage.repository import (
    ClaimedEvent,
    ClaimedJob,
    StorageRepository,
)


class JobRepository(Protocol):
    def claim_job(self, worker_name: str) -> ClaimedJob | None: ...

    def load_record(self, feedback_id: str) -> FeedbackRecord: ...

    def persist_success(
        self,
        job: ClaimedJob,
        envelope: dict[str, Any],
        event: dict[str, Any],
        *,
        traceparent: str | None = None,
        tracestate: str | None = None,
    ) -> None: ...

    def persist_failure(self, job: ClaimedJob, error: Exception) -> None: ...

    def claim_event(self, worker_name: str) -> ClaimedEvent | None: ...

    def persist_projection_success(self, event: ClaimedEvent, destination: str) -> None: ...

    def persist_projection_failure(self, event: ClaimedEvent, error: Exception) -> None: ...


class ProjectionClient(Protocol):
    def insert_event(self, event: dict[str, Any]) -> None: ...


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    postgres_dsn: str
    clickhouse_url: str
    clickhouse_user: str
    clickhouse_password: str
    schema_path: Path
    fixture_path: Path
    worker_name: str
    poll_seconds: float = 1.0

    @classmethod
    def from_environment(cls) -> WorkerSettings:
        root = find_repository_root()
        return cls(
            postgres_dsn=_required_environment("POSTGRES_DSN"),
            clickhouse_url=_required_environment("CLICKHOUSE_URL"),
            clickhouse_user=_required_environment("CLICKHOUSE_USER"),
            clickhouse_password=_required_environment("CLICKHOUSE_PASSWORD"),
            schema_path=root / "schemas/feedback-decision/1.0.0/manifest.json",
            fixture_path=root / "data/fixtures/decisions/demo-semif-qwen3.5-4b-mlx-q4.json",
            worker_name=os.getenv("WORKER_NAME", f"decision-worker-{socket.gethostname()}"),
            poll_seconds=_poll_seconds(os.getenv("WORKER_POLL_SECONDS", "1")),
        )


@dataclass(frozen=True, slots=True)
class DrainResult:
    jobs_claimed: int = 0
    jobs_succeeded: int = 0
    jobs_failed: int = 0
    events_claimed: int = 0
    events_projected: int = 0
    events_skipped: int = 0
    events_failed: int = 0

    @property
    def had_work(self) -> bool:
        return self.jobs_claimed > 0 or self.events_claimed > 0


EngineFactory = Callable[[str, str], DecisionEngine]
NOOP_TELEMETRY = WorkerTelemetry(enabled=False, endpoint="", service_name="")


def drain_once(
    repository: JobRepository,
    projector: ProjectionClient,
    schema: DecisionSchema,
    engine_factory: EngineFactory,
    worker_name: str,
    telemetry: WorkerTelemetry = NOOP_TELEMETRY,
) -> DrainResult:
    result = DrainResult()
    job = repository.claim_job(worker_name)
    if job is not None:
        try:
            parent = telemetry.parent_context(job.traceparent, job.tracestate)
            with telemetry.span(
                "feedback.process",
                {
                    "job.id": job.job_id,
                    "feedback.id": job.feedback_id,
                    "decision.engine": job.engine,
                    "schema.version": job.decision_schema_version,
                    "attempt.count": job.attempt_count,
                },
                parent=parent,
            ) as process_span:
                try:
                    if (
                        job.decision_schema_name != schema.name
                        or job.decision_schema_version != schema.version
                        or job.decision_schema_sha256 != schema.sha256
                    ):
                        raise ValueError(
                            "Claimed job decision schema does not match the loaded manifest"
                        )
                    record = repository.load_record(job.feedback_id)
                    with telemetry.span(
                        "feedback.redact",
                        {
                            "feedback.id": job.feedback_id,
                            "source.type": record.source.provider_id,
                        },
                    ):
                        state = PrivacyBoundary().prepare_for_decision(record)
                    engine = engine_factory(job.engine, job.requested_model)
                    with telemetry.span(
                        "decision.evaluate",
                        {
                            "feedback.id": job.feedback_id,
                            "decision.engine": job.engine,
                            "model.version": job.requested_model,
                            "schema.version": schema.version,
                        },
                    ):
                        decision = engine.decide(state, schema)
                    envelope = build_decision_envelope(state, schema, decision)
                    event = build_signal_projection_event(record, envelope)
                    with telemetry.span(
                        "decision.persist",
                        {
                            "feedback.id": job.feedback_id,
                            "decision.id": envelope["decision_id"],
                            "decision.engine": job.engine,
                            "latency.ms": decision.latency_ms,
                        },
                    ):
                        traceparent, tracestate = telemetry.current_context_carrier()
                        repository.persist_success(
                            job,
                            envelope,
                            event,
                            traceparent=traceparent,
                            tracestate=tracestate,
                        )
                    telemetry.record_decision(
                        engine=job.engine,
                        latency_ms=decision.latency_ms,
                    )
                except Exception as error:
                    telemetry.mark_error(process_span, error)
                    raise
            result = DrainResult(jobs_claimed=1, jobs_succeeded=1)
            _event("decision.succeeded", job_id=job.job_id, engine=job.engine)
        except Exception as error:
            repository.persist_failure(job, error)
            telemetry.record_decision_error(engine=job.engine, error=error)
            result = DrainResult(jobs_claimed=1, jobs_failed=1)
            _event(
                "decision.failed",
                job_id=job.job_id,
                engine=job.engine,
                error_type=type(error).__name__,
            )

    claimed_event = repository.claim_event(f"{worker_name}-projector")
    if claimed_event is None:
        return result

    try:
        projection_parent = telemetry.parent_context(
            claimed_event.traceparent,
            claimed_event.tracestate,
        )
        with telemetry.span(
            "analytics.project",
            {
                "event.id": claimed_event.event_id,
                "attempt.count": claimed_event.attempt_count,
            },
            parent=projection_parent,
        ) as projection_span:
            try:
                eligibility = claimed_event.payload.get("eligibility")
                if not isinstance(eligibility, dict):
                    raise ValueError("Projection event eligibility must be an object")
                if any(value is True for value in eligibility.values()):
                    projector.insert_event(claimed_event.payload)
                    destination = "clickhouse.signal_facts"
                    projected = 1
                    skipped = 0
                else:
                    destination = "skipped.uncalibrated"
                    projected = 0
                    skipped = 1
                if projection_span is not None:
                    projection_span.set_attribute("destination", destination)
                repository.persist_projection_success(claimed_event, destination)
            except Exception as error:
                telemetry.mark_error(projection_span, error)
                raise
        telemetry.record_projection(destination=destination, outcome="succeeded")
        _event("projection.succeeded", event_id=claimed_event.event_id, destination=destination)
        return DrainResult(
            jobs_claimed=result.jobs_claimed,
            jobs_succeeded=result.jobs_succeeded,
            jobs_failed=result.jobs_failed,
            events_claimed=1,
            events_projected=projected,
            events_skipped=skipped,
        )
    except Exception as error:
        repository.persist_projection_failure(claimed_event, error)
        telemetry.record_projection(destination="unknown", outcome="failed")
        _event(
            "projection.failed",
            event_id=claimed_event.event_id,
            error_type=type(error).__name__,
        )
        return DrainResult(
            jobs_claimed=result.jobs_claimed,
            jobs_succeeded=result.jobs_succeeded,
            jobs_failed=result.jobs_failed,
            events_claimed=1,
            events_failed=1,
        )


def run(settings: WorkerSettings, *, once: bool = False) -> int:
    schema = load_decision_schema(settings.schema_path)
    engine_factory = build_engine_factory(settings.fixture_path)
    projector = ClickHouseClient(
        settings.clickhouse_url,
        settings.clickhouse_user,
        settings.clickhouse_password,
    )
    telemetry = WorkerTelemetry.from_environment()
    stop_requested = False

    def request_stop(_signal_number: int, _frame: FrameType | None) -> None:
        nonlocal stop_requested
        stop_requested = True

    previous_sigterm = signal.signal(signal.SIGTERM, request_stop)
    previous_sigint = signal.signal(signal.SIGINT, request_stop)
    _event("worker.started", worker_name=settings.worker_name, once=once)
    try:
        with StorageRepository(settings.postgres_dsn) as repository:
            while not stop_requested:
                result = drain_once(
                    repository,
                    projector,
                    schema,
                    engine_factory,
                    settings.worker_name,
                    telemetry,
                )
                if once:
                    _event("worker.drain_complete", **asdict(result))
                    return 0 if result.jobs_failed == 0 and result.events_failed == 0 else 1
                if not result.had_work:
                    time.sleep(settings.poll_seconds)
        _event("worker.stopped", worker_name=settings.worker_name)
        return 0
    finally:
        telemetry.shutdown()
        signal.signal(signal.SIGTERM, previous_sigterm)
        signal.signal(signal.SIGINT, previous_sigint)


def build_engine_factory(fixture_path: Path) -> EngineFactory:
    def create(engine: str, requested_model: str) -> DecisionEngine:
        return create_decision_engine(
            engine,
            requested_model=requested_model,
            fixture_path=fixture_path,
        )

    return create


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _poll_seconds(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise ValueError("WORKER_POLL_SECONDS must be numeric") from error
    if not 0.1 <= parsed <= 60:
        raise ValueError("WORKER_POLL_SECONDS must be between 0.1 and 60")
    return parsed


def _event(name: str, **attributes: object) -> None:
    print(json.dumps({"event": name, **attributes}, sort_keys=True), flush=True)
