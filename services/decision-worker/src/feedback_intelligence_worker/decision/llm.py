"""General-purpose LLM baseline through the System One Adapter."""

from __future__ import annotations

import os
import re
from time import perf_counter
from typing import Literal, cast

from system_one_adapter import RetryPolicy, SystemOneAdapterClient
from typesafe_sdk import JSONValue

from feedback_intelligence_worker.decision.models import (
    DecisionEngineResult,
    DecisionResultError,
    validate_engine_result,
)
from feedback_intelligence_worker.decision.schema import DecisionSchema
from feedback_intelligence_worker.decision.system_one import (
    map_system_one_response,
    question_payloads,
)
from feedback_intelligence_worker.privacy.models import ModelSafeFeedbackState

LLM_PROVIDER: Literal["openai"] = "openai"
LLM_MODEL = "gpt-5.4-mini-2026-03-17"
_PINNED_MODEL = re.compile(r".*-\d{4}-\d{2}-\d{2}$")


class LlmSystemOneDecisionEngine:
    """Execute the frozen typed questions through a pinned OpenAI model."""

    provider_id = "llm-openai"

    def __init__(
        self,
        *,
        model: str = LLM_MODEL,
        client: SystemOneAdapterClient | None = None,
    ) -> None:
        if not _PINNED_MODEL.fullmatch(model.strip()):
            raise ValueError("LlmSystemOneDecisionEngine requires an explicit dated model snapshot")
        self._model = model
        self._client = client

    def decide(
        self,
        state: ModelSafeFeedbackState,
        schema: DecisionSchema,
    ) -> DecisionEngineResult:
        outbound_state = cast(dict[str, JSONValue], state.to_decision_state())
        if not set(outbound_state) <= set(schema.allowed_state_fields):
            raise DecisionResultError("Model-safe state exceeds decision schema allow-list")
        questions = question_payloads(schema)
        started = perf_counter()
        if self._client is None:
            if not os.getenv("OPENAI_API_KEY", "").strip():
                raise ValueError("OPENAI_API_KEY is required for the live LLM baseline")
            retry = RetryPolicy(max_retries=2, timeout=60.0)
            with SystemOneAdapterClient(
                structured_outputs=True,
                llm_answer_mode="probabilities",
                normalize_probabilities=True,
                n_retry_malformed_structure=2,
                retry=retry,
            ) as client:
                response = client.system_one(
                    state=outbound_state,
                    questions=questions,
                    provider=LLM_PROVIDER,
                    model=self._model,
                )
        else:
            response = self._client.system_one(
                state=outbound_state,
                questions=questions,
                provider=LLM_PROVIDER,
                model=self._model,
            )
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        result = map_system_one_response(
            response,
            provider=self.provider_id,
            requested_model=self._model,
            latency_ms=latency_ms,
            input_tokens=response.usage.input_tokens_total,
            output_tokens=response.usage.output_tokens_total,
        )
        validate_engine_result(result, schema)
        return result
