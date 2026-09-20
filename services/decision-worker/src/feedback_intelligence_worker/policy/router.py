"""Route validated decision answers through a calibrated policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from feedback_intelligence_worker.decision.models import (
    ChoiceDecision,
    DecisionAnswer,
    NoulDecision,
    ScoreDecision,
)
from feedback_intelligence_worker.policy.models import (
    AggregationPolicy,
    ConfidenceThresholds,
    PolicyNotCalibratedError,
    PolicyStatus,
    ProbabilityThresholds,
)

type RouteState = Literal[
    "accepted",
    "review",
    "abstained",
    "accepted_positive",
    "accepted_negative",
    "uncertain",
]


@dataclass(frozen=True, slots=True)
class PolicyRoute:
    question_id: str
    state: RouteState
    policy_version: str
    policy_sha256: str


def route_answer(
    policy: AggregationPolicy,
    question_id: str,
    answer: DecisionAnswer,
) -> PolicyRoute:
    question = policy.question(question_id)
    if policy.status is not PolicyStatus.ACTIVE or question.thresholds is None:
        raise PolicyNotCalibratedError(
            f"Policy {policy.identity} is {policy.status.value}; routing is disabled"
        )
    if isinstance(answer, NoulDecision) and isinstance(question.thresholds, ProbabilityThresholds):
        state: RouteState
        if answer.noul <= question.thresholds.negative_max:
            state = "accepted_negative"
        elif answer.noul >= question.thresholds.positive_min:
            state = "accepted_positive"
        else:
            state = "uncertain"
    elif isinstance(answer, (ChoiceDecision, ScoreDecision)) and isinstance(
        question.thresholds, ConfidenceThresholds
    ):
        if answer.confidence >= question.thresholds.accept_min:
            state = "accepted"
        elif answer.confidence >= question.thresholds.review_min:
            state = "review"
        else:
            state = "abstained"
    else:
        raise PolicyNotCalibratedError(f"Answer type does not match policy for {question_id}")
    return PolicyRoute(question_id, state, policy.version, policy.sha256)
