"""Local SemIf adapter using pinned Qwen3.5 option-logit scoring."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from time import perf_counter
from typing import Any, Protocol

from feedback_intelligence_worker.decision.models import (
    ChoiceDecision,
    DecisionAnswer,
    DecisionEngineResult,
    DecisionResultError,
    NoulDecision,
    ScoreDecision,
    validate_engine_result,
)
from feedback_intelligence_worker.decision.schema import DecisionSchema, Primitive, QuestionSpec
from feedback_intelligence_worker.privacy.models import ModelSafeFeedbackState

SEMIF_CODE_REVISION = "ca3ba65f142967030ecb453346e94d6f476a69df"
SEMIF_MODEL_SOURCE = "Qwen/Qwen3.5-4B"
SEMIF_MODEL_REVISION = "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"
SEMIF_MODEL = "semif-qwen3.5-4b-mlx-q4-851bf6e8"


class SemifScorer(Protocol):
    def score(self, rows: Sequence[Mapping[str, Any]]) -> Sequence[Mapping[str, Any]]: ...


class MlxSemifScorer:
    """Load the pinned model once and reuse each record's state prefix serially."""

    def __init__(
        self,
        *,
        source: str = SEMIF_MODEL_SOURCE,
        revision: str = SEMIF_MODEL_REVISION,
        bits: int = 4,
        cache_limit_mib: int = 128,
    ) -> None:
        self._source = source
        self._revision = revision
        self._bits = bits
        self._cache_limit_mib = cache_limit_mib
        self._scorer: Any | None = None
        self._load_error: Exception | None = None

    def score(self, rows: Sequence[Mapping[str, Any]]) -> Sequence[Mapping[str, Any]]:
        scorer = self._load()
        return [scorer.score(dict(row)) for row in rows]

    def _load(self) -> Any:
        if self._scorer is not None:
            return self._scorer
        if self._load_error is not None:
            raise self._load_error
        try:
            from semif_phase1 import mlx_backend

            model, tokenizer, metadata = mlx_backend.load_model(
                self._source,
                self._revision,
                self._bits,
                cache_limit_mib=self._cache_limit_mib,
            )
            self._scorer = mlx_backend.SerialPrefixScorer(model, tokenizer, metadata)
            return self._scorer
        except Exception as error:
            self._load_error = error
            raise


class SemifDecisionEngine:
    """Translate the feedback schema into SemIf's runtime option interface."""

    provider_id = "semif"

    def __init__(
        self,
        *,
        model: str = SEMIF_MODEL,
        scorer: SemifScorer | None = None,
    ) -> None:
        if model != SEMIF_MODEL:
            raise ValueError(f"SemifDecisionEngine supports only {SEMIF_MODEL}")
        self._model = model
        self._scorer = scorer or MlxSemifScorer()

    def decide(
        self,
        state: ModelSafeFeedbackState,
        schema: DecisionSchema,
    ) -> DecisionEngineResult:
        outbound_state = state.to_decision_state()
        if not set(outbound_state) <= set(schema.allowed_state_fields):
            raise DecisionResultError("Model-safe state exceeds decision schema allow-list")
        rows = [_question_row(outbound_state, question) for question in schema.questions]
        started = perf_counter()
        raw_results = self._scorer.score(rows)
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        by_id = {_text(result, "id"): result for result in raw_results}
        expected = {question.question_id for question in schema.questions}
        if set(by_id) != expected:
            raise DecisionResultError("SemIf result ids do not match the decision schema")
        answers = {
            question.question_id: _map_answer(question, by_id[question.question_id])
            for question in schema.questions
        }
        input_tokens = sum(_integer(result, "input_tokens") for result in raw_results)
        decision = DecisionEngineResult(
            provider=self.provider_id,
            requested_model=self._model,
            resolved_model=self._model,
            answers=answers,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=0,
        )
        validate_engine_result(decision, schema)
        return decision


def _question_row(state: Mapping[str, object], question: QuestionSpec) -> dict[str, Any]:
    if question.primitive is Primitive.CHOICE:
        options = [
            {"id": option.option_id, "description": option.description}
            for option in question.options
        ]
    elif question.primitive is Primitive.SCORE:
        options = [
            {
                "id": str(level.value),
                "description": f"{level.label}: {level.description}",
            }
            for level in question.levels
        ]
    else:
        if question.true_criteria is None or question.false_criteria is None:
            raise DecisionResultError(f"Boolean criteria are missing for {question.question_id}")
        options = [
            {"id": "true", "description": question.true_criteria},
            {"id": "false", "description": question.false_criteria},
        ]
    return {
        "id": question.question_id,
        "state": dict(state),
        "question": question.instructions,
        "options": options,
    }


def _map_answer(question: QuestionSpec, result: Mapping[str, Any]) -> DecisionAnswer:
    option_ids = result.get("option_ids")
    raw_probabilities = result.get("probabilities")
    if not isinstance(option_ids, list) or not isinstance(raw_probabilities, list):
        raise DecisionResultError(
            f"SemIf result is missing probabilities for {question.question_id}"
        )
    if len(option_ids) != len(raw_probabilities) or len(option_ids) < 2:
        raise DecisionResultError(f"SemIf result shape is invalid for {question.question_id}")
    probabilities: dict[str, float] = {}
    for option_id, raw_probability in zip(option_ids, raw_probabilities, strict=True):
        if not isinstance(option_id, str):
            raise DecisionResultError(f"SemIf option id is invalid for {question.question_id}")
        probability = float(raw_probability)
        if not math.isfinite(probability):
            raise DecisionResultError(f"SemIf probability is nonfinite for {question.question_id}")
        probabilities[option_id] = probability
    confidence = max(probabilities.values())
    if question.primitive is Primitive.CHOICE:
        allowed_options = [option.option_id for option in question.options]
        if set(probabilities) != set(allowed_options):
            raise DecisionResultError(f"SemIf choice options differ for {question.question_id}")
        choice = max(allowed_options, key=probabilities.__getitem__)
        return ChoiceDecision(choice=choice, probabilities=probabilities, confidence=confidence)
    if question.primitive is Primitive.SCORE:
        allowed_levels = [level.value for level in question.levels]
        if set(probabilities) != {str(value) for value in allowed_levels}:
            raise DecisionResultError(f"SemIf score levels differ for {question.question_id}")
        numeric: dict[int, float] = {value: probabilities[str(value)] for value in allowed_levels}
        score = sum(value * probability for value, probability in numeric.items())
        legend = {level.value: level.label for level in question.levels}
        return ScoreDecision(
            score=score,
            probabilities=numeric,
            confidence=confidence,
            legend=legend,
        )
    if set(probabilities) != {"true", "false"}:
        raise DecisionResultError(f"SemIf boolean options differ for {question.question_id}")
    return NoulDecision(noul=probabilities["true"])


def _text(value: Mapping[str, Any], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw:
        raise DecisionResultError(f"SemIf result field {key} must be nonempty text")
    return raw


def _integer(value: Mapping[str, Any], key: str) -> int:
    raw = value.get(key)
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        raise DecisionResultError(f"SemIf result field {key} must be a nonnegative integer")
    return raw
