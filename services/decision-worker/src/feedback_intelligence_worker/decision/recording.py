"""Write credential-free recordings of real engine outputs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from feedback_intelligence_worker.decision.models import DecisionEngineResult
from feedback_intelligence_worker.decision.schema import DecisionSchema
from feedback_intelligence_worker.privacy.models import ModelSafeFeedbackState


def write_fixture_set(
    path: Path,
    *,
    schema: DecisionSchema,
    recordings: list[tuple[ModelSafeFeedbackState, DecisionEngineResult]],
    force: bool = False,
) -> None:
    if not recordings:
        raise ValueError("At least one decision recording is required")
    if path.exists() and not force:
        raise FileExistsError(f"Decision fixture already exists: {path}; pass --force")
    providers = {result.provider for _, result in recordings}
    requested_models = {result.requested_model for _, result in recordings}
    resolved_models = {result.resolved_model for _, result in recordings}
    if len(providers) != 1 or len(requested_models) != 1 or len(resolved_models) != 1:
        raise ValueError("One fixture set must use one provider and model identity")
    payload: dict[str, Any] = {
        "fixture_format": "decision-fixture-set/1.0.0",
        "schema_name": schema.name,
        "schema_version": schema.version,
        "schema_sha256": schema.sha256,
        "recorded_provider": next(iter(providers)),
        "requested_model": next(iter(requested_models)),
        "resolved_model": next(iter(resolved_models)),
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "records": {
            state.redacted_text_sha256: {
                "answers": {
                    question_id: answer.to_dict()
                    for question_id, answer in sorted(result.answers.items())
                }
            }
            for state, result in recordings
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
