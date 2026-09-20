"""Evaluation scorer contract, metrics, and leakage-gate tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from feedback_intelligence_worker.decision.schema import (
    DecisionSchema,
    Primitive,
    load_decision_schema,
)
from feedback_intelligence_worker.evaluation.scoring import score_evaluation


@pytest.fixture(scope="module")
def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def schema(repository_root: Path) -> DecisionSchema:
    return load_decision_schema(repository_root / "schemas/feedback-decision/1.0.0/manifest.json")


def test_perfect_predictions_produce_complete_primitive_metrics(
    tmp_path: Path, schema: DecisionSchema
) -> None:
    paths = _fixture(tmp_path, schema, split="development")

    report = score_evaluation(
        records_path=paths[0],
        labels_path=paths[1],
        predictions_path=paths[2],
        schema=schema,
        split="development",
    )

    assert report["summary"]["record_count"] == 2
    assert report["summary"]["primary_topic_accuracy"] == 1.0
    assert report["summary"]["primary_topic_macro_f1"] > 0
    assert report["questions"]["overall_experience"]["mae"] == 0.0
    assert report["questions"]["mentions_delivery"]["f1"] == 1.0
    assert report["questions"]["mentions_delivery"]["auroc"] == 1.0
    assert report["operations"]["latency_ms"] == {"p50": 15.0, "p95": 19.5, "p99": 19.9}
    assert len(report["report_sha256"]) == 64


def test_locked_test_requires_explicit_unlock(tmp_path: Path, schema: DecisionSchema) -> None:
    records, labels, predictions = _fixture(tmp_path, schema, split="locked_test")

    with pytest.raises(ValueError, match="unlock-locked-test"):
        score_evaluation(
            records_path=records,
            labels_path=labels,
            predictions_path=predictions,
            schema=schema,
            split="locked_test",
        )


def test_prediction_ids_must_exactly_match_split(tmp_path: Path, schema: DecisionSchema) -> None:
    records, labels, predictions = _fixture(tmp_path, schema, split="calibration")
    rows = predictions.read_text().splitlines()
    predictions.write_text(rows[0] + "\n")

    with pytest.raises(ValueError, match="Prediction ids do not match"):
        score_evaluation(
            records_path=records,
            labels_path=labels,
            predictions_path=predictions,
            schema=schema,
            split="calibration",
        )


def test_partial_scoring_is_explicit_and_limited_to_ai_reference(
    tmp_path: Path, schema: DecisionSchema
) -> None:
    records, labels, predictions = _fixture(tmp_path, schema, split="development")
    rows = predictions.read_text().splitlines()
    predictions.write_text(rows[0] + "\n")

    report = score_evaluation(
        records_path=records,
        labels_path=labels,
        predictions_path=predictions,
        schema=schema,
        split="development",
        reference_kind="ai_reference",
        reference_model="reference-v1",
        allow_partial=True,
    )

    assert report["partial_evaluation"] is True
    assert report["summary"]["record_count"] == 1
    assert report["summary"]["target_record_count"] == 2

    with pytest.raises(ValueError, match="only available for an AI reference"):
        score_evaluation(
            records_path=records,
            labels_path=labels,
            predictions_path=predictions,
            schema=schema,
            split="development",
            allow_partial=True,
        )


def test_prediction_failures_remain_in_quality_denominator(
    tmp_path: Path, schema: DecisionSchema
) -> None:
    records, labels, predictions = _fixture(tmp_path, schema, split="development")
    rows = [json.loads(line) for line in predictions.read_text().splitlines()]
    rows[1]["status"] = "error"
    rows[1]["answers"] = None
    rows[1]["error_type"] = "provider_timeout"
    predictions.write_text("".join(json.dumps(row) + "\n" for row in rows))

    report = score_evaluation(
        records_path=records,
        labels_path=labels,
        predictions_path=predictions,
        schema=schema,
        split="development",
    )

    assert report["summary"]["success_count"] == 1
    assert report["summary"]["error_count"] == 1
    assert report["summary"]["primary_topic_accuracy"] == 0.5
    assert report["questions"]["primary_topic"]["evaluated_count"] == 1
    assert report["operations"]["errors_by_type"] == {"provider_timeout": 1}


def _fixture(tmp_path: Path, schema: DecisionSchema, *, split: str) -> tuple[Path, Path, Path]:
    ids = ["00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002"]
    records: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    for index, feedback_id in enumerate(ids):
        records.append(
            {
                "schema_version": "feedback-evaluation-sample/1.0.0",
                "feedback_id": feedback_id,
                "feedback_text": f"example {index}",
                "language": "en-GB" if index == 0 else "sv-SE",
                "channel": "product_review",
                "split": split,
                "requires_second_pass": False,
            }
        )
        gold, predicted = _answers(schema, index)
        labels.append(
            {
                "schema_version": "feedback-annotation-record/1.0.0",
                "feedback_id": feedback_id,
                "split": split,
                "requires_second_pass": False,
                "annotations": [
                    {
                        "annotator_id": "reviewer-a",
                        "pass": 1,
                        "annotated_at": "2026-09-19T00:00:00Z",
                        "answers": gold,
                    }
                ],
                "adjudication": None,
            }
        )
        predictions.append(
            {
                "schema_version": "feedback-evaluation-prediction/1.0.0",
                "feedback_id": feedback_id,
                "split": split,
                "engine": {
                    "provider": "test",
                    "requested_model": "test-v1",
                    "resolved_model": "test-v1",
                    "run_id": "test-run",
                    "schema_sha256": schema.sha256,
                },
                "status": "success",
                "answers": predicted,
                "error_type": None,
                "execution": {
                    "latency_ms": 10 + index * 10,
                    "input_tokens": 5,
                    "output_tokens": 2,
                    "cost_usd": 0.001,
                },
            }
        )
    paths = (tmp_path / "records.jsonl", tmp_path / "labels.jsonl", tmp_path / "predictions.jsonl")
    for path, rows in zip(paths, (records, labels, predictions), strict=True):
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return paths


def _answers(schema: DecisionSchema, index: int) -> tuple[dict[str, Any], dict[str, Any]]:
    gold: dict[str, Any] = {}
    predicted: dict[str, Any] = {}
    for question in schema.questions:
        if question.primitive is Primitive.CHOICE:
            options = [option.option_id for option in question.options]
            choice_value = options[index % len(options)]
            gold[question.question_id] = {"type": "choice", "value": choice_value}
            predicted[question.question_id] = {
                "type": "choice",
                "choice": choice_value,
                "probabilities": {option: float(option == choice_value) for option in options},
                "confidence": 1.0,
            }
        elif question.primitive is Primitive.SCORE:
            levels = [level.value for level in question.levels]
            score_value = levels[index % len(levels)]
            gold[question.question_id] = {"type": "score", "value": score_value}
            predicted[question.question_id] = {
                "type": "score",
                "score": score_value,
                "probabilities": {str(level): float(level == score_value) for level in levels},
                "confidence": 1.0,
            }
        else:
            noul_value = bool(index)
            gold[question.question_id] = {"type": "noul", "value": noul_value}
            predicted[question.question_id] = {
                "type": "noul",
                "noul": float(noul_value),
            }
    return gold, predicted
