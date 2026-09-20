"""Build persistence-safe decision envelopes without feedback bodies."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid5

from feedback_intelligence_worker.decision.models import DecisionEngineResult
from feedback_intelligence_worker.decision.schema import DecisionSchema
from feedback_intelligence_worker.privacy.models import ModelSafeFeedbackState

DECISION_ID_NAMESPACE = UUID("0141545f-a124-449f-bc7c-127203629f97")


def build_decision_envelope(
    state: ModelSafeFeedbackState,
    schema: DecisionSchema,
    result: DecisionEngineResult,
    *,
    decided_at: datetime | None = None,
) -> dict[str, Any]:
    identity = ":".join(
        (
            state.feedback_id,
            schema.sha256,
            result.provider,
            result.resolved_model,
            state.redacted_text_sha256,
        )
    )
    timestamp = decided_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("decided_at must include a timezone")
    return {
        "envelope_version": "feedback-decision-envelope/1.0.0",
        "decision_id": str(uuid5(DECISION_ID_NAMESPACE, identity)),
        "feedback_id": state.feedback_id,
        "decided_at": timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "schema": {
            "name": schema.name,
            "version": schema.version,
            "sha256": schema.sha256,
        },
        "engine": {
            "provider": result.provider,
            "recorded_provider": result.recorded_provider,
            "requested_model": result.requested_model,
            "resolved_model": result.resolved_model,
        },
        "input": {
            "redacted_text_sha256": state.redacted_text_sha256,
            "language": state.language,
            "channel": state.channel,
        },
        "answers": {
            question_id: answer.to_dict() for question_id, answer in sorted(result.answers.items())
        },
        "policy": None,
        "execution": {
            "request_id": result.request_id,
            "latency_ms": result.latency_ms,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        },
    }
