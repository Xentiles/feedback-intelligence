"""Evaluation sampling and uncalibrated policy safety tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from feedback_intelligence_worker.decision.models import ChoiceDecision
from feedback_intelligence_worker.decision.schema import load_decision_schema
from feedback_intelligence_worker.evaluation.annotations import validate_annotation_readiness
from feedback_intelligence_worker.policy import (
    PolicyNotCalibratedError,
    load_aggregation_policy,
    route_answer,
)


@pytest.fixture(scope="module")
def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_frozen_sample_has_exact_splits_and_checksum(repository_root: Path) -> None:
    directory = repository_root / "evaluation/datasets/feedback-decision-1.0.0"
    manifest = json.loads((directory / "selection-manifest.json").read_text())
    records = (directory / "records.jsonl").read_bytes()
    rows = [json.loads(line) for line in records.splitlines()]

    assert len(rows) == 480
    assert manifest["split_counts"] == {
        "development": 300,
        "calibration": 80,
        "locked_test": 100,
    }
    assert manifest["double_annotated_counts"] == {
        "development": 75,
        "calibration": 20,
        "locked_test": 25,
    }
    assert hashlib.sha256(records).hexdigest() == manifest["records_sha256"]
    assert all("scenario_id" not in row and "synthetic_event_id" not in row for row in rows)
    assert sum(row["requires_second_pass"] for row in rows) == 120


def test_empty_human_template_blocks_calibration(repository_root: Path) -> None:
    directory = repository_root / "evaluation/datasets/feedback-decision-1.0.0"
    schema = load_decision_schema(repository_root / "schemas/feedback-decision/1.0.0/manifest.json")

    readiness = validate_annotation_readiness(
        directory / "records.jsonl", directory / "labels.jsonl", schema
    )

    assert readiness.total == 480
    assert readiness.complete == 0
    assert readiness.ready_for_calibration is False


def test_uncalibrated_policy_cannot_route_model_output(repository_root: Path) -> None:
    schema = load_decision_schema(repository_root / "schemas/feedback-decision/1.0.0/manifest.json")
    policy = load_aggregation_policy(
        repository_root / "schemas/aggregation-policy/1.0.0/manifest.json", schema
    )
    answer = ChoiceDecision(
        choice="other",
        probabilities={
            "product_quality": 0.01,
            "compatibility": 0.01,
            "delivery": 0.01,
            "support": 0.01,
            "returns_refunds": 0.01,
            "price_value": 0.01,
            "website_checkout": 0.01,
            "product_information": 0.01,
            "other": 0.92,
        },
        confidence=0.92,
    )

    with pytest.raises(PolicyNotCalibratedError, match="routing is disabled"):
        route_answer(policy, "primary_topic", answer)
