"""Persistence-boundary and analytical projection contract tests."""

from __future__ import annotations

import json
from pathlib import Path

from feedback_intelligence_worker.data.providers.synthetic import SyntheticDatasetProvider
from feedback_intelligence_worker.decision.envelope import build_decision_envelope
from feedback_intelligence_worker.decision.fixture import FixtureDecisionEngine
from feedback_intelligence_worker.decision.schema import load_decision_schema
from feedback_intelligence_worker.privacy import PrivacyBoundary
from feedback_intelligence_worker.storage.events import (
    build_signal_projection_event,
    event_to_clickhouse_row,
)


def test_projection_event_is_stable_text_free_and_uncalibrated() -> None:
    root = Path(__file__).resolve().parents[3]
    record = SyntheticDatasetProvider(root / "data/demo/feedback.jsonl").load_feedback().records[0]
    schema = load_decision_schema(root / "schemas/feedback-decision/1.0.0/manifest.json")
    state = PrivacyBoundary().prepare_for_decision(record)
    fixture = root / "data/fixtures/decisions/demo-semif-qwen3.5-4b-mlx-q4.json"
    result = FixtureDecisionEngine(fixture).decide(state, schema)
    envelope = build_decision_envelope(state, schema, result)

    first = build_signal_projection_event(record, envelope)
    second = build_signal_projection_event(record, envelope)
    serialized = json.dumps(first)

    assert first == second
    assert first["event_version"] == "signal-projection-event/1.1.0"
    assert first["decision_time"] == envelope["decided_at"]
    assert first["source"] == {
        "provider_id": record.source.provider_id,
        "dataset_name": record.source.dataset_name,
        "dataset_version": record.source.dataset_version,
    }
    assert first["policy"] == {"status": "uncalibrated", "version": None}
    assert not any(first["eligibility"].values())
    assert all(value is None for value in first["accepted_positive"].values())
    assert record.original_text not in serialized
    assert state.redacted_text not in serialized
    for forbidden in (
        "feedback_text",
        "original_text",
        "redacted_text",
        "source_record_id",
        "scenario_id",
    ):
        assert forbidden not in serialized

    row = event_to_clickhouse_row(first)
    assert row["primary_topic_eligible"] == 0
    assert row["primary_topic_accepted_positive"] is None
    assert row["product_defect_eligible"] == 0
    assert row["product_defect_accepted_positive"] is None
    assert row["policy_status"] == "uncalibrated"
    assert row["decision_time"] == first["decision_time"].replace("T", " ").removesuffix("Z")[:-3]
    assert row["source_provider_id"] == record.source.provider_id
    assert row["source_dataset_name"] == record.source.dataset_name
    assert row["source_dataset_version"] == record.source.dataset_version


def test_clickhouse_row_requires_explicit_accepted_positive_boolean() -> None:
    root = Path(__file__).resolve().parents[3]
    record = SyntheticDatasetProvider(root / "data/demo/feedback.jsonl").load_feedback().records[0]
    schema = load_decision_schema(root / "schemas/feedback-decision/1.0.0/manifest.json")
    state = PrivacyBoundary().prepare_for_decision(record)
    fixture = root / "data/fixtures/decisions/demo-semif-qwen3.5-4b-mlx-q4.json"
    result = FixtureDecisionEngine(fixture).decide(state, schema)
    event = build_signal_projection_event(record, build_decision_envelope(state, schema, result))
    event["accepted_positive"]["product_defect"] = 0.9

    try:
        event_to_clickhouse_row(event)
    except ValueError as error:
        assert str(error) == "accepted_positive values must be boolean or null"
    else:
        raise AssertionError("probabilities must not become accepted classifications")
