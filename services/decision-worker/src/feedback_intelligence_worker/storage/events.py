"""Build the text-free analytical projection contract from a decision."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid5

from feedback_intelligence_worker.data.models import FeedbackRecord, utc_iso

EVENT_NAMESPACE = UUID("89096892-e418-47bb-a1f1-175df12bb279")
PROJECTION_NAMESPACE = UUID("fdaf1b10-d60d-4790-bfd5-2b2dccd06567")
TRACE_NAMESPACE = UUID("a362b80e-1574-468b-9564-543957d0e337")

ELIGIBILITY_KEYS = (
    "primary_topic",
    "overall_experience",
    "delivery_experience",
    "support_experience",
    "product_defect",
    "actionable",
    "severity",
    "resolution",
)


def build_signal_projection_event(
    record: FeedbackRecord,
    envelope: dict[str, Any],
) -> dict[str, Any]:
    """Create a projection payload; uncalibrated answers are never aggregate-eligible."""
    decision_id = _text(envelope, "decision_id")
    event_id = str(uuid5(EVENT_NAMESPACE, decision_id))
    projection_id = str(uuid5(PROJECTION_NAMESPACE, event_id))
    trace_id = str(uuid5(TRACE_NAMESPACE, decision_id))
    answers = _object(envelope.get("answers"), "answers")
    schema = _object(envelope.get("schema"), "schema")
    engine = _object(envelope.get("engine"), "engine")
    policy = envelope.get("policy")
    if policy is not None:
        raise ValueError("Projection of calibrated policy decisions is not implemented yet")
    product = record.related_products[0] if record.related_products else None
    return {
        "event_version": "signal-projection-event/1.1.0",
        "event_id": event_id,
        "projection_id": projection_id,
        "event_time": utc_iso(record.occurred_at),
        "feedback_id": record.feedback_id,
        "decision_id": decision_id,
        "decision_time": _text(envelope, "decided_at"),
        "source": {
            "provider_id": record.source.provider_id,
            "dataset_name": record.source.dataset_name,
            "dataset_version": record.source.dataset_version,
        },
        "dimensions": {
            "product_id": None if product is None else product.product_id,
            "product_family": None if product is None else product.category,
            "source_type": record.channel or "unknown",
            "locale": record.language or "und",
        },
        "signals": {
            "primary_topic": _choice(answers, "primary_topic"),
            "primary_topic_confidence": _confidence(answers, "primary_topic"),
            "overall_negative_probability": _negative_probability(answers, "overall_experience"),
            "delivery_negative_probability": _negative_probability(answers, "delivery_experience"),
            "support_negative_probability": _negative_probability(answers, "support_experience"),
            "product_defect_probability": _noul(answers, "reports_product_defect"),
            "actionable_probability": _noul(answers, "actionable_feedback"),
            "severity_score": _score(answers, "issue_severity"),
            "resolution_status": _choice(answers, "resolution_status"),
        },
        "eligibility": dict.fromkeys(ELIGIBILITY_KEYS, False),
        "accepted_positive": dict.fromkeys(ELIGIBILITY_KEYS),
        "policy": {"status": "uncalibrated", "version": None},
        "provenance": {
            "schema_version": _text(schema, "version"),
            "model_version": _text(engine, "resolved_model"),
        },
        "trace_id": trace_id,
    }


def event_to_clickhouse_row(event: dict[str, Any]) -> dict[str, Any]:
    source = _object(event.get("source"), "source")
    dimensions = _object(event.get("dimensions"), "dimensions")
    signals = _object(event.get("signals"), "signals")
    eligibility = _object(event.get("eligibility"), "eligibility")
    accepted_positive = _object(event.get("accepted_positive"), "accepted_positive")
    policy = _object(event.get("policy"), "policy")
    provenance = _object(event.get("provenance"), "provenance")
    return {
        "projection_id": event["projection_id"],
        "event_id": event["event_id"],
        "event_time": _clickhouse_timestamp(event["event_time"]),
        "feedback_id": event["feedback_id"],
        "decision_id": event["decision_id"],
        "decision_time": _clickhouse_timestamp(event["decision_time"]),
        "source_provider_id": source["provider_id"],
        "source_dataset_name": source["dataset_name"],
        "source_dataset_version": source["dataset_version"],
        "product_id": dimensions["product_id"],
        "product_family": dimensions["product_family"],
        "source_type": dimensions["source_type"],
        "locale": dimensions["locale"],
        "primary_topic": signals["primary_topic"],
        "primary_topic_confidence": signals["primary_topic_confidence"],
        "primary_topic_eligible": int(bool(eligibility["primary_topic"])),
        "primary_topic_accepted_positive": _nullable_bool_int(accepted_positive["primary_topic"]),
        "overall_negative_probability": signals["overall_negative_probability"],
        "overall_experience_eligible": int(bool(eligibility["overall_experience"])),
        "overall_experience_accepted_positive": _nullable_bool_int(
            accepted_positive["overall_experience"]
        ),
        "delivery_negative_probability": signals["delivery_negative_probability"],
        "delivery_experience_eligible": int(bool(eligibility["delivery_experience"])),
        "delivery_experience_accepted_positive": _nullable_bool_int(
            accepted_positive["delivery_experience"]
        ),
        "support_negative_probability": signals["support_negative_probability"],
        "support_experience_eligible": int(bool(eligibility["support_experience"])),
        "support_experience_accepted_positive": _nullable_bool_int(
            accepted_positive["support_experience"]
        ),
        "product_defect_probability": signals["product_defect_probability"],
        "product_defect_eligible": int(bool(eligibility["product_defect"])),
        "product_defect_accepted_positive": _nullable_bool_int(accepted_positive["product_defect"]),
        "actionable_probability": signals["actionable_probability"],
        "actionable_eligible": int(bool(eligibility["actionable"])),
        "actionable_accepted_positive": _nullable_bool_int(accepted_positive["actionable"]),
        "severity_score": signals["severity_score"],
        "severity_eligible": int(bool(eligibility["severity"])),
        "severity_accepted_positive": _nullable_bool_int(accepted_positive["severity"]),
        "resolution_status": signals["resolution_status"],
        "resolution_eligible": int(bool(eligibility["resolution"])),
        "resolution_accepted_positive": _nullable_bool_int(accepted_positive["resolution"]),
        "policy_status": policy["status"],
        "policy_version": policy["version"],
        "schema_version": provenance["schema_version"],
        "model_version": provenance["model_version"],
        "trace_id": event["trace_id"],
    }


def _answer(answers: dict[str, Any], question_id: str) -> dict[str, Any]:
    return _object(answers.get(question_id), question_id)


def _choice(answers: dict[str, Any], question_id: str) -> str:
    return _text(_answer(answers, question_id), "choice")


def _confidence(answers: dict[str, Any], question_id: str) -> float:
    return _number(_answer(answers, question_id), "confidence")


def _score(answers: dict[str, Any], question_id: str) -> float:
    return _number(_answer(answers, question_id), "score")


def _noul(answers: dict[str, Any], question_id: str) -> float:
    return _number(_answer(answers, question_id), "noul")


def _negative_probability(answers: dict[str, Any], question_id: str) -> float:
    answer = _answer(answers, question_id)
    probabilities = _object(answer.get("probabilities"), f"{question_id}.probabilities")
    return float(probabilities.get("0", 0)) + float(probabilities.get("1", 0))


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: dict[str, Any], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"{key} must be text")
    return raw


def _number(value: dict[str, Any], key: str) -> float:
    raw = value.get(key)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(raw)


def _clickhouse_timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("event_time must be text")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized).astimezone(UTC)
    return parsed.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _nullable_bool_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError("accepted_positive values must be boolean or null")
    return int(value)
