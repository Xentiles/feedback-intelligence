"""Provider-neutral typed decision answers and execution metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from feedback_intelligence_worker.decision.schema import DecisionSchema, Primitive


class DecisionResultError(ValueError):
    """Raised when an engine returns an answer outside the frozen schema."""


@dataclass(frozen=True, slots=True)
class ChoiceDecision:
    choice: str
    probabilities: dict[str, float]
    confidence: float
    type: str = "choice"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "choice": self.choice,
            "probabilities": dict(sorted(self.probabilities.items())),
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class ScoreDecision:
    score: float
    probabilities: dict[int, float]
    confidence: float
    legend: dict[int, str]
    type: str = "score"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "score": self.score,
            "probabilities": {str(key): value for key, value in sorted(self.probabilities.items())},
            "confidence": self.confidence,
            "legend": {str(key): value for key, value in sorted(self.legend.items())},
        }


@dataclass(frozen=True, slots=True)
class NoulDecision:
    noul: float
    type: str = "noul"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "noul": self.noul}


type DecisionAnswer = ChoiceDecision | ScoreDecision | NoulDecision


@dataclass(frozen=True, slots=True)
class DecisionEngineResult:
    provider: str
    requested_model: str
    resolved_model: str
    answers: dict[str, DecisionAnswer]
    latency_ms: int
    request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    recorded_provider: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "requested_model": self.requested_model,
            "resolved_model": self.resolved_model,
            "recorded_provider": self.recorded_provider,
            "answers": {
                question_id: answer.to_dict()
                for question_id, answer in sorted(self.answers.items())
            },
            "execution": {
                "latency_ms": self.latency_ms,
                "request_id": self.request_id,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
            },
        }


def validate_engine_result(result: DecisionEngineResult, schema: DecisionSchema) -> None:
    expected_ids = {question.question_id for question in schema.questions}
    if set(result.answers) != expected_ids:
        missing = sorted(expected_ids - set(result.answers))
        extra = sorted(set(result.answers) - expected_ids)
        raise DecisionResultError(
            f"Answer ids do not match schema; missing={missing}, extra={extra}"
        )
    for question in schema.questions:
        answer = result.answers[question.question_id]
        if question.primitive is Primitive.CHOICE:
            if not isinstance(answer, ChoiceDecision):
                raise DecisionResultError(f"Wrong primitive for {question.question_id}")
            allowed = {option.option_id for option in question.options}
            if answer.choice not in allowed or set(answer.probabilities) != allowed:
                raise DecisionResultError(f"Invalid choice output for {question.question_id}")
            _probability(answer.confidence, f"{question.question_id}.confidence")
            _distribution(answer.probabilities, question.question_id)
        elif question.primitive is Primitive.SCORE:
            if not isinstance(answer, ScoreDecision):
                raise DecisionResultError(f"Wrong primitive for {question.question_id}")
            allowed_levels = {level.value for level in question.levels}
            if set(answer.probabilities) != allowed_levels or set(answer.legend) != allowed_levels:
                raise DecisionResultError(f"Invalid score distribution for {question.question_id}")
            if not 0 <= answer.score <= max(allowed_levels):
                raise DecisionResultError(f"Score outside rubric for {question.question_id}")
            _probability(answer.confidence, f"{question.question_id}.confidence")
            _distribution(answer.probabilities, question.question_id)
        else:
            if not isinstance(answer, NoulDecision):
                raise DecisionResultError(f"Wrong primitive for {question.question_id}")
            _probability(answer.noul, f"{question.question_id}.noul")


def _probability(value: float, label: str) -> None:
    if not 0 <= value <= 1:
        raise DecisionResultError(f"{label} must be within [0, 1]")


def _distribution(values: dict[str, float] | dict[int, float], label: str) -> None:
    for value in values.values():
        _probability(value, f"{label}.probabilities")
    if abs(sum(values.values()) - 1.0) > 0.02:
        raise DecisionResultError(f"{label} probabilities must sum approximately to one")
