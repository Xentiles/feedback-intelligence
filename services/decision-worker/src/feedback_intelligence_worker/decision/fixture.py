"""Credential-free adapter for previously recorded decision outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from feedback_intelligence_worker.decision.models import (
    ChoiceDecision,
    DecisionAnswer,
    DecisionEngineResult,
    NoulDecision,
    ScoreDecision,
    validate_engine_result,
)
from feedback_intelligence_worker.decision.schema import DecisionSchema
from feedback_intelligence_worker.privacy.models import ModelSafeFeedbackState


class FixtureDecisionError(ValueError):
    """Raised when a recording is absent or incompatible with the request."""


class FixtureDecisionEngine:
    provider_id = "fixture"

    def __init__(self, fixture_path: Path) -> None:
        if not fixture_path.is_file():
            raise FixtureDecisionError(f"Decision fixture does not exist: {fixture_path}")
        value = json.loads(fixture_path.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or value.get("fixture_format") != "decision-fixture-set/1.0.0"
        ):
            raise FixtureDecisionError("Unsupported decision fixture format")
        self._fixture = value

    def decide(
        self,
        state: ModelSafeFeedbackState,
        schema: DecisionSchema,
    ) -> DecisionEngineResult:
        if self._fixture.get("schema_sha256") != schema.sha256:
            raise FixtureDecisionError("Fixture decision schema hash does not match")
        records = self._fixture.get("records")
        if not isinstance(records, dict):
            raise FixtureDecisionError("Fixture records must be an object")
        value = records.get(state.redacted_text_sha256)
        if not isinstance(value, dict):
            raise FixtureDecisionError(
                f"No recorded decision for input hash {state.redacted_text_sha256}"
            )
        answers_value = value.get("answers")
        if not isinstance(answers_value, dict):
            raise FixtureDecisionError("Recorded answers must be an object")
        answers = {
            question_id: _answer_from_dict(answer)
            for question_id, answer in answers_value.items()
            if isinstance(question_id, str)
        }
        result = DecisionEngineResult(
            provider="fixture",
            recorded_provider=_required_text(self._fixture, "recorded_provider"),
            requested_model=_required_text(self._fixture, "requested_model"),
            resolved_model=_required_text(self._fixture, "resolved_model"),
            answers=answers,
            latency_ms=0,
        )
        validate_engine_result(result, schema)
        return result


def _answer_from_dict(value: object) -> DecisionAnswer:
    if not isinstance(value, dict):
        raise FixtureDecisionError("Recorded answer must be an object")
    answer_type = value.get("type")
    if answer_type == "choice":
        return ChoiceDecision(
            choice=_required_text(value, "choice"),
            probabilities=_string_probabilities(value.get("probabilities")),
            confidence=_number(value, "confidence"),
        )
    if answer_type == "score":
        legend_value = value.get("legend")
        if not isinstance(legend_value, dict):
            raise FixtureDecisionError("Recorded score legend must be an object")
        return ScoreDecision(
            score=_number(value, "score"),
            probabilities=_integer_probabilities(value.get("probabilities")),
            confidence=_number(value, "confidence"),
            legend={int(key): str(item) for key, item in legend_value.items()},
        )
    if answer_type == "noul":
        return NoulDecision(noul=_number(value, "noul"))
    raise FixtureDecisionError(f"Unsupported recorded answer type: {answer_type!r}")


def _required_text(value: dict[str, Any], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise FixtureDecisionError(f"Fixture field {key} must be non-blank text")
    return raw


def _number(value: dict[str, Any], key: str) -> float:
    raw = value.get(key)
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        raise FixtureDecisionError(f"Fixture field {key} must be numeric")
    return float(raw)


def _string_probabilities(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        raise FixtureDecisionError("Choice probabilities must be an object")
    return {str(key): _probability_value(item) for key, item in value.items()}


def _integer_probabilities(value: object) -> dict[int, float]:
    if not isinstance(value, dict):
        raise FixtureDecisionError("Score probabilities must be an object")
    return {int(key): _probability_value(item) for key, item in value.items()}


def _probability_value(value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise FixtureDecisionError("Probability must be numeric")
    return float(value)
