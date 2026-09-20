"""Run one decision engine over the frozen evaluation records."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from feedback_intelligence_worker.decision.engine import DecisionEngine
from feedback_intelligence_worker.decision.schema import DecisionSchema
from feedback_intelligence_worker.privacy.boundary import PrivacyBoundary

PREDICTION_FORMAT = "feedback-evaluation-prediction/1.0.0"


def run_evaluation_predictions(
    *,
    records_path: Path,
    output_path: Path,
    schema: DecisionSchema,
    engine: DecisionEngine,
    requested_model: str,
    force: bool = False,
    resume: bool = False,
    limit: int | None = None,
    request_delay_seconds: float = 0.0,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Write checkpointed prediction rows while keeping record text out of output."""
    if force and resume:
        raise ValueError("--force and --resume cannot be combined")
    if limit is not None and limit < 1:
        raise ValueError("--limit must be positive")
    if request_delay_seconds < 0:
        raise ValueError("--request-delay-seconds must be non-negative")
    records = _records(records_path)
    selected = records[:limit]
    existing = _existing(output_path) if resume else {}
    if output_path.exists() and not force and not resume:
        raise ValueError(f"Prediction output already exists: {output_path}")
    known_ids = {row["feedback_id"] for row in records}
    if not set(existing) <= known_ids:
        raise ValueError("Existing prediction output contains unknown feedback ids")

    run_id = hashlib.sha256(
        f"{requested_model}:{schema.sha256}:{_sha256(records_path)}".encode()
    ).hexdigest()[:24]
    engine_metadata = {
        "provider": engine.provider_id,
        "requested_model": requested_model,
        "resolved_model": requested_model,
        "run_id": run_id,
        "schema_sha256": schema.sha256,
    }
    for row in existing.values():
        if row.get("engine") != engine_metadata:
            raise ValueError("Existing prediction output uses different engine metadata")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if resume else "w"
    success_count = sum(row.get("status") == "success" for row in existing.values())
    error_count = sum(row.get("status") == "error" for row in existing.values())
    processed = 0
    with output_path.open(mode, encoding="utf-8", newline="\n") as destination:
        for record in selected:
            feedback_id = _text(record, "feedback_id")
            if feedback_id in existing:
                continue
            prediction = _predict_record(record, schema, engine, engine_metadata)
            destination.write(
                json.dumps(prediction, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )
            destination.flush()
            processed += 1
            success_count += int(prediction["status"] == "success")
            error_count += int(prediction["status"] == "error")
            if progress is not None and (processed == 1 or processed % 25 == 0):
                progress(len(existing) + processed, len(selected))
            if request_delay_seconds and len(existing) + processed < len(selected):
                time.sleep(request_delay_seconds)

    return {
        "schema_version": PREDICTION_FORMAT,
        "run_id": run_id,
        "records_selected": len(selected),
        "records_preexisting": len(existing),
        "records_processed": processed,
        "success_count": success_count,
        "error_count": error_count,
        "output": str(output_path),
    }


def _predict_record(
    record: dict[str, Any],
    schema: DecisionSchema,
    engine: DecisionEngine,
    engine_metadata: dict[str, Any],
) -> dict[str, Any]:
    feedback_id = _text(record, "feedback_id")
    try:
        state = PrivacyBoundary().prepare_text(
            feedback_id=feedback_id,
            text=_text(record, "feedback_text"),
            source_provider_id="evaluation-ai-reference",
            language=_text(record, "language"),
            channel=_text(record, "channel"),
        )
        result = engine.decide(state, schema)
        if result.provider != engine_metadata["provider"]:
            raise ValueError("Decision provider differs from prediction metadata")
        if result.requested_model != engine_metadata["requested_model"]:
            raise ValueError("Requested model differs from prediction metadata")
        if result.resolved_model != engine_metadata["resolved_model"]:
            raise ValueError("Resolved model differs from the pinned prediction model")
        return {
            "schema_version": PREDICTION_FORMAT,
            "feedback_id": feedback_id,
            "split": _text(record, "split"),
            "engine": engine_metadata,
            "status": "success",
            "answers": {
                question_id: answer.to_dict()
                for question_id, answer in sorted(result.answers.items())
            },
            "error_type": None,
            "execution": {
                "latency_ms": result.latency_ms,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": None,
            },
        }
    except Exception as error:  # provider failures are benchmark outcomes
        return {
            "schema_version": PREDICTION_FORMAT,
            "feedback_id": feedback_id,
            "split": _text(record, "split"),
            "engine": engine_metadata,
            "status": "error",
            "answers": None,
            "error_type": type(error).__name__,
            "execution": {
                "latency_ms": 0,
                "input_tokens": None,
                "output_tokens": None,
                "cost_usd": None,
            },
        }


def _records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"Evaluation records do not exist: {path}")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Expected object at {path}:{number}")
        feedback_id = _text(value, "feedback_id")
        if feedback_id in seen:
            raise ValueError(f"Duplicate feedback id at {path}:{number}")
        seen.add(feedback_id)
        records.append(value)
    return records


def _existing(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    result: dict[str, dict[str, Any]] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Expected prediction object at {path}:{number}")
        feedback_id = _text(value, "feedback_id")
        if feedback_id in result:
            raise ValueError(f"Duplicate existing prediction id at {path}:{number}")
        result[feedback_id] = value
    return result


def _text(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"{key} must be non-blank text")
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
