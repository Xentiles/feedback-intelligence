"""Decision engine port consumed by worker orchestration."""

from __future__ import annotations

from typing import Protocol

from feedback_intelligence_worker.decision.models import DecisionEngineResult
from feedback_intelligence_worker.decision.schema import DecisionSchema
from feedback_intelligence_worker.privacy.models import ModelSafeFeedbackState


class DecisionEngine(Protocol):
    provider_id: str

    def decide(
        self,
        state: ModelSafeFeedbackState,
        schema: DecisionSchema,
    ) -> DecisionEngineResult: ...
