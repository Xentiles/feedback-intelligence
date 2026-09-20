"""Canonical feedback contract tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from feedback_intelligence_worker.data.models import (
    CanonicalRecordError,
    FeedbackRecord,
    Rating,
    SourceReference,
    canonical_feedback_id,
)


def test_canonical_record_serializes_required_fields_and_round_trips() -> None:
    source = SourceReference(
        provider_id="test",
        dataset_name="Test data",
        dataset_version="1.0.0",
        source_record_id="source-1",
    )
    record = FeedbackRecord(
        feedback_id=canonical_feedback_id("test", "source-1"),
        source=source,
        original_text="A useful feedback record.",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        rating=Rating(Decimal(4), Decimal(1), Decimal(5)),
        language="en-GB",
    )

    payload = record.to_dict()

    assert set(payload) == {
        "schema_version",
        "feedback_id",
        "source",
        "original_text",
        "title",
        "occurred_at",
        "rating",
        "related_products",
        "order_id",
        "channel",
        "language",
        "metadata",
        "operational_context",
        "privacy_status",
    }
    assert payload["privacy_status"] == "uninspected"
    assert FeedbackRecord.from_dict(payload) == record


def test_record_rejects_naive_timestamp() -> None:
    with pytest.raises(CanonicalRecordError, match="timezone"):
        FeedbackRecord(
            feedback_id=canonical_feedback_id("test", "source-1"),
            source=SourceReference("test", "Test", "1", "source-1"),
            original_text="Text",
            occurred_at=datetime(2026, 1, 1),
        )


def test_record_rejects_model_ready_privacy_status_from_provider() -> None:
    with pytest.raises(CanonicalRecordError, match="uninspected"):
        FeedbackRecord(
            feedback_id=canonical_feedback_id("test", "source-1"),
            source=SourceReference("test", "Test", "1", "source-1"),
            original_text="Text",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            privacy_status="redacted",
        )


def test_rating_must_fit_declared_scale() -> None:
    with pytest.raises(CanonicalRecordError, match="outside"):
        Rating(Decimal(6), Decimal(1), Decimal(5))
