"""Checkpointed evaluation prediction-runner tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from feedback_intelligence_worker.decision.models import (
    ChoiceDecision,
    DecisionAnswer,
    DecisionEngineResult,
    NoulDecision,
    ScoreDecision,
)
from feedback_intelligence_worker.decision.schema import (
    DecisionSchema,
    Primitive,
    load_decision_schema,
)
from feedback_intelligence_worker.evaluation.predict import run_evaluation_predictions
from feedback_intelligence_worker.privacy.models import ModelSafeFeedbackState, RedactionKind


class FakeEngine:
    provider_id = "test-provider"

    def __init__(self) -> None:
        self.states: list[ModelSafeFeedbackState] = []

    def decide(self, state: ModelSafeFeedbackState, schema: DecisionSchema) -> DecisionEngineResult:
        self.states.append(state)
        answers: dict[str, DecisionAnswer] = {}
        for question in schema.questions:
            if question.primitive is Primitive.CHOICE:
                options = [option.option_id for option in question.options]
                answers[question.question_id] = ChoiceDecision(
                    choice=options[0],
                    probabilities={value: float(index == 0) for index, value in enumerate(options)},
                    confidence=1.0,
                )
            elif question.primitive is Primitive.SCORE:
                levels = [level.value for level in question.levels]
                answers[question.question_id] = ScoreDecision(
                    score=float(levels[0]),
                    probabilities={value: float(index == 0) for index, value in enumerate(levels)},
                    confidence=1.0,
                    legend={level.value: level.label for level in question.levels},
                )
            else:
                answers[question.question_id] = NoulDecision(noul=0.0)
        return DecisionEngineResult(
            provider="test-provider",
            requested_model="test-model-1.0.0",
            resolved_model="test-model-1.0.0",
            answers=answers,
            latency_ms=12,
            input_tokens=20,
            output_tokens=0,
        )


def test_prediction_runner_writes_contract_rows_without_feedback_text(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    schema = load_decision_schema(root / "schemas/feedback-decision/1.0.0/manifest.json")
    records = tmp_path / "records.jsonl"
    records.write_text(
        json.dumps(
            {
                "feedback_id": "00000000-0000-4000-8000-000000000001",
                "feedback_text": "A private test sentence that must not be written.",
                "language": "en-GB",
                "channel": "product_review",
                "split": "development",
            }
        )
        + "\n"
    )
    output = tmp_path / "predictions.jsonl"

    result = run_evaluation_predictions(
        records_path=records,
        output_path=output,
        schema=schema,
        engine=FakeEngine(),
        requested_model="test-model-1.0.0",
    )

    row = json.loads(output.read_text())
    assert result["success_count"] == 1
    assert row["status"] == "success"
    assert row["engine"]["schema_sha256"] == schema.sha256
    assert "private test sentence" not in output.read_text().lower()
    assert len(row["answers"]) == 14


def test_prediction_runner_resume_does_not_repeat_completed_rows(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    schema = load_decision_schema(root / "schemas/feedback-decision/1.0.0/manifest.json")
    records = tmp_path / "records.jsonl"
    records.write_text(
        json.dumps(
            {
                "feedback_id": "00000000-0000-4000-8000-000000000001",
                "feedback_text": "Works well.",
                "language": "en-GB",
                "channel": "product_review",
                "split": "development",
            }
        )
        + "\n"
    )
    output = tmp_path / "predictions.jsonl"
    first = run_evaluation_predictions(
        records_path=records,
        output_path=output,
        schema=schema,
        engine=FakeEngine(),
        requested_model="test-model-1.0.0",
    )
    second = run_evaluation_predictions(
        records_path=records,
        output_path=output,
        schema=schema,
        engine=FakeEngine(),
        requested_model="test-model-1.0.0",
        resume=True,
    )

    assert first["records_processed"] == 1
    assert second["records_processed"] == 0
    assert len(output.read_text().splitlines()) == 1


@pytest.mark.parametrize(
    ("text", "expected_error"),
    [
        ("Email canary@example.com about the delivery.", None),
        ("Card 4111 1111 1111 1111", "PaymentDataDetectedError"),
        ("CVV: 123", "PaymentDataDetectedError"),
        ("IBAN SE45 5000 0000 0583 9825 7466", "PaymentDataDetectedError"),
    ],
)
def test_evaluation_applies_privacy_before_engine_call(
    tmp_path: Path, text: str, expected_error: str | None
) -> None:
    root = Path(__file__).resolve().parents[3]
    schema = load_decision_schema(root / "schemas/feedback-decision/1.0.0/manifest.json")
    records = tmp_path / "records.jsonl"
    records.write_text(
        json.dumps(
            {
                "feedback_id": "00000000-0000-4000-8000-000000000001",
                "feedback_text": text,
                "language": "canary@example.com",
                "channel": "CVV: 123",
                "split": "development",
            }
        )
        + "\n"
    )
    output = tmp_path / "predictions.jsonl"
    engine = FakeEngine()
    run_evaluation_predictions(
        records_path=records,
        output_path=output,
        schema=schema,
        engine=engine,
        requested_model="test-model-1.0.0",
    )
    row = json.loads(output.read_text())
    assert row["error_type"] == expected_error
    assert text not in output.read_text()
    if expected_error:
        assert engine.states == []
        assert row["status"] == "error"
    else:
        assert row["status"] == "success"
        assert len(engine.states) == 1
        state = engine.states[0]
        assert state.to_decision_state() == {"feedback_text": "Email [EMAIL] about the delivery."}
        assert state.redactions.counts[RedactionKind.EMAIL] == 1
