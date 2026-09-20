"""Shared typed-question and response mapping for the LLM baseline adapter."""

from __future__ import annotations

from collections.abc import Mapping

from typesafe_sdk import (
    Choice,
    ChoiceAnswer,
    Noul,
    NoulAnswer,
    Score,
    ScoreAnswer,
    SystemOneResponse,
    TypeSafeError,
)

from feedback_intelligence_worker.decision.models import (
    ChoiceDecision,
    DecisionAnswer,
    DecisionEngineResult,
    DecisionResultError,
    NoulDecision,
    ScoreDecision,
)
from feedback_intelligence_worker.decision.schema import DecisionSchema, Primitive, QuestionSpec


def _typed_question(question: QuestionSpec) -> Choice | Score | Noul:
    if question.primitive is Primitive.CHOICE:
        return Choice(
            instructions=question.instructions,
            criteria={option.option_id: option.description for option in question.options},
        )
    if question.primitive is Primitive.SCORE:
        return Score(
            instructions=question.instructions,
            criteria=[level.description for level in question.levels],
        )
    return Noul(
        instructions=question.instructions,
        criteria={"true": question.true_criteria, "false": question.false_criteria},
    )


def map_system_one_response(
    response: SystemOneResponse,
    *,
    provider: str,
    requested_model: str,
    latency_ms: int,
    input_tokens: int,
    output_tokens: int,
) -> DecisionEngineResult:
    answers: dict[str, DecisionAnswer] = {}
    for question_id, answer in response.answers.items():
        if isinstance(answer, ChoiceAnswer):
            answers[question_id] = ChoiceDecision(
                choice=answer.choice,
                probabilities=dict(answer.probabilities),
                confidence=answer.confidence,
            )
        elif isinstance(answer, ScoreAnswer):
            if not all(isinstance(value, str) for value in answer.legend.values()):
                raise DecisionResultError(f"Non-text score legend returned for {question_id}")
            answers[question_id] = ScoreDecision(
                score=answer.score,
                probabilities=dict(answer.probabilities),
                confidence=answer.confidence,
                legend={
                    key: value for key, value in answer.legend.items() if isinstance(value, str)
                },
            )
        elif isinstance(answer, NoulAnswer):
            answers[question_id] = NoulDecision(noul=answer.noul)
        else:
            raise DecisionResultError(f"Unsupported typed answer for {question_id}")
    try:
        request_id = response.request_id
    except TypeSafeError:
        request_id = None
    return DecisionEngineResult(
        provider=provider,
        requested_model=requested_model,
        resolved_model=response.model,
        answers=answers,
        latency_ms=latency_ms,
        request_id=request_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def question_payloads(schema: DecisionSchema) -> Mapping[str, Choice | Score | Noul]:
    """Build the exact typed questions used by the general-purpose LLM baseline."""
    return {question.question_id: _typed_question(question) for question in schema.questions}
