"""PII canary tests for the local pre-provider boundary."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from _pytest.capture import CaptureFixture
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from feedback_intelligence_worker.data.models import (
    FeedbackRecord,
    Rating,
    RelatedProduct,
    SourceReference,
    canonical_feedback_id,
)
from feedback_intelligence_worker.privacy import (
    DeterministicRedactor,
    PaymentDataDetectedError,
    PrivacyBoundary,
    RedactionKind,
)
from feedback_intelligence_worker.privacy.cli import main
from feedback_intelligence_worker.privacy.models import PrivacyBoundaryError
from feedback_intelligence_worker.privacy.telemetry import (
    WorkerTelemetry,
    redaction_event,
    safe_metric_attributes,
    safe_trace_attributes,
)


def feedback(text: str) -> FeedbackRecord:
    return FeedbackRecord(
        feedback_id=canonical_feedback_id("test", "privacy-canary"),
        source=SourceReference("test", "Privacy fixtures", "1.0.0", "privacy-canary"),
        original_text=text,
        title="Private title is deliberately excluded",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        rating=Rating(Decimal(1), Decimal(1), Decimal(5)),
        related_products=(RelatedProduct(product_id="PRIVATE-SKU-42"),),
        order_id="PRIVATE-ORDER-FIELD",
        channel="support_ticket",
        language="sv-SE",
        metadata={"scenario_id": "PRIVATE-SCENARIO-FIELD"},
    )


def test_redactor_removes_supported_pii_without_retaining_values() -> None:
    source = (
        "Jag heter Anna Andersson. E-post anna.andersson@example.se. "
        "Ring +46 70 123 45 67. Personnummer 900101-1239. "
        "Customer ID CUST-9012 and order number ORD-778899. "
        "Leverera till Storgatan 12, 123 45 Stockholm."
    )

    redacted, summary = DeterministicRedactor().redact_text(source)

    for private_value in (
        "Anna Andersson",
        "anna.andersson@example.se",
        "+46 70 123 45 67",
        "900101-1239",
        "CUST-9012",
        "ORD-778899",
        "Storgatan 12",
        "123 45 Stockholm",
    ):
        assert private_value not in redacted
        assert private_value not in repr(summary)
    assert {
        "[NAME]",
        "[EMAIL]",
        "[PHONE]",
        "[NATIONAL_ID]",
        "[CUSTOMER_ID]",
        "[ORDER_ID]",
        "[ADDRESS]",
    } <= set(redacted.replace(",", "").replace(".", "").split())
    assert summary.counts[RedactionKind.ADDRESS] == 2
    assert summary.total == 8


@pytest.mark.parametrize(
    "source",
    [
        "Card 4111 1111 1111 1111 was used.",
        "CVV: 123",
        "Refund to IBAN SE45 5000 0000 0583 9825 7466.",
    ],
)
def test_payment_data_is_rejected_instead_of_redacted(source: str) -> None:
    with pytest.raises(PaymentDataDetectedError, match="remove payment data"):
        PrivacyBoundary().prepare_for_decision(feedback(source))


def test_model_state_is_minimal_and_does_not_expose_source_fields() -> None:
    record = feedback(
        "My name is Alice Example. Email alice@example.com about order number ORD-4400."
    )

    prepared = PrivacyBoundary().prepare_for_decision(record)
    state = prepared.to_decision_state()

    assert state == {
        "feedback_text": "My name is [NAME]. Email [EMAIL] about order number [ORDER_ID].",
        "language": "sv-SE",
        "channel": "support_ticket",
    }
    serialized = json.dumps(state)
    for prohibited in (
        record.original_text,
        record.title,
        record.order_id,
        record.related_products[0].product_id,
        "PRIVATE-SCENARIO-FIELD",
        record.feedback_id,
        record.source.source_record_id,
    ):
        assert prohibited is not None
        assert prohibited not in serialized
    assert prepared.redacted_text not in repr(prepared)


def test_canaries_do_not_reach_mock_outbound_request_or_telemetry() -> None:
    private_values = {
        "canary.person@example.com",
        "+46 73 555 12 34",
        "900101-1239",
        "CANARY-4477",
        "ORDER-998877",
    }
    record = feedback(
        "Contact canary.person@example.com or +46 73 555 12 34. "
        "Personnummer 900101-1239, customer ID CANARY-4477, "
        "order number ORDER-998877."
    )
    prepared = PrivacyBoundary().prepare_for_decision(record)

    captured_outbound_request = json.dumps(prepared.to_decision_state())
    captured_telemetry = json.dumps(redaction_event(prepared))

    for private_value in private_values:
        assert private_value not in captured_outbound_request
        assert private_value not in captured_telemetry
    assert "feedback_text" not in captured_telemetry
    assert "[EMAIL]" not in captured_telemetry
    assert record.original_text not in captured_telemetry


def test_telemetry_allow_lists_drop_content_credentials_and_metric_identifiers() -> None:
    trace_attributes = safe_trace_attributes(
        {
            "feedback.id": "safe-trace-identifier",
            "decision.engine": "rules",
            "raw_text": "PRIVATE RAW BODY",
            "redacted_text": "[EMAIL]",
            "api_key": "PRIVATE KEY",
            "customer_id": "PRIVATE CUSTOMER",
        }
    )
    metric_attributes = safe_metric_attributes(
        {
            "feedback.id": "high-cardinality-id",
            "decision.engine": "rules",
            "error.type": "TimeoutError",
            "raw_text": "PRIVATE RAW BODY",
        }
    )

    assert trace_attributes == {
        "feedback.id": "safe-trace-identifier",
        "decision.engine": "rules",
    }
    assert metric_attributes == {
        "decision.engine": "rules",
        "error.type": "TimeoutError",
    }


def test_worker_extracts_the_persisted_w3c_parent_context() -> None:
    parent = WorkerTelemetry.parent_context(
        "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
        None,
    )

    span_context = trace.get_current_span(parent).get_span_context()

    assert span_context.trace_id == int("0af7651916cd43dd8448eb211c80319c", 16)
    assert span_context.span_id == int("b7ad6b7169203331", 16)
    assert span_context.is_remote


def test_redaction_and_hash_are_deterministic() -> None:
    record = feedback("Email the team at privacy@example.com.")
    boundary = PrivacyBoundary()

    first = boundary.prepare_for_decision(record)
    second = boundary.prepare_for_decision(record)

    assert first == second
    assert first.redacted_text_sha256 == (
        "sha256:05c2fa286ebe653b4c2d6de134158f30280a5a2b8c708f002c48f6e95a878f7c"
    )


def test_privacy_cli_checks_demo_without_external_calls(
    capsys: CaptureFixture[str],
) -> None:
    assert main(["synthetic", "--json"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output == {
        "external_calls": 0,
        "prepared_records": 9,
        "provider_id": "synthetic",
        "records_checked": 9,
        "redactions": {},
        "rejected_payment_data": 0,
    }


@pytest.mark.parametrize("field", ["language", "channel"])
@pytest.mark.parametrize("private_value", ["canary@example.com", "4111 1111 1111 1111", "CVV: 123"])
def test_untrusted_metadata_never_reaches_model_state(field: str, private_value: str) -> None:
    source = feedback("Works well.")
    record = (
        replace(source, language=private_value)
        if field == "language"
        else replace(source, channel=private_value)
    )
    prepared = PrivacyBoundary().prepare_for_decision(record)
    assert field not in prepared.to_decision_state()
    assert private_value not in json.dumps(prepared.to_decision_state())
    assert getattr(record, field) == private_value  # source metadata stays local and unchanged
    with pytest.raises(PrivacyBoundaryError):
        if field == "language":
            replace(prepared, language=private_value)
        else:
            replace(prepared, channel=private_value)


def test_nested_span_export_omits_exception_messages_stacks_and_status_descriptions() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry = WorkerTelemetry(enabled=False, endpoint="unused", service_name="privacy-test")
    telemetry.enabled = True
    telemetry._tracer = provider.get_tracer("test")
    secret = "canary-provider-body@example.com"
    try:
        with (
            pytest.raises(ValueError, match=secret),
            telemetry.span("feedback.process", {"raw_text": secret}),
            telemetry.span("decision.evaluate", {}),
        ):
            raise ValueError(secret)
        spans = exporter.get_finished_spans()
        assert len(spans) == 2
        for span in spans:
            assert span.status.status_code is trace.StatusCode.ERROR
            assert span.status.description is None
            assert span.events == ()
            assert dict(span.attributes or {}) == {"error.type": "ValueError"}
            assert secret not in span.to_json()
    finally:
        provider.shutdown()
