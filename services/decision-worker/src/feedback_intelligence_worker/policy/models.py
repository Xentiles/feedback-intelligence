"""Load and cross-check an aggregation policy against its decision schema."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from feedback_intelligence_worker.decision.schema import DecisionSchema, Primitive


class PolicyError(ValueError):
    """Raised when a policy is structurally or semantically invalid."""


class PolicyNotCalibratedError(PolicyError):
    """Raised when an inactive policy is used to route an answer."""


class PolicyStatus(StrEnum):
    AWAITING_CALIBRATION = "awaiting_calibration"
    ACTIVE = "active"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class ConfidenceThresholds:
    review_min: float
    accept_min: float


@dataclass(frozen=True, slots=True)
class ProbabilityThresholds:
    negative_max: float
    positive_min: float


type Thresholds = ConfidenceThresholds | ProbabilityThresholds


@dataclass(frozen=True, slots=True)
class QuestionPolicy:
    question_id: str
    primitive: Primitive
    routing: str
    thresholds: Thresholds | None


@dataclass(frozen=True, slots=True)
class AggregationPolicy:
    name: str
    version: str
    status: PolicyStatus
    decision_schema_version: str
    decision_schema_sha256: str
    questions: tuple[QuestionPolicy, ...]
    calibration_dataset_sha256: str | None
    calibration_labels_sha256: str | None
    sha256: str

    @property
    def identity(self) -> str:
        return f"{self.name}/{self.version}"

    def question(self, question_id: str) -> QuestionPolicy:
        for question in self.questions:
            if question.question_id == question_id:
                return question
        raise PolicyError(f"Unknown policy question: {question_id}")


def load_aggregation_policy(path: Path, schema: DecisionSchema) -> AggregationPolicy:
    if not path.is_file():
        raise PolicyError(f"Aggregation policy does not exist: {path}")
    source = path.read_bytes()
    try:
        payload = json.loads(source)
    except json.JSONDecodeError as error:
        raise PolicyError(f"Invalid aggregation policy JSON: {error}") from error
    if not isinstance(payload, dict):
        raise PolicyError("Aggregation policy must be an object")
    if payload.get("manifest_format") != "aggregation-policy-manifest/1.0.0":
        raise PolicyError("Unsupported aggregation policy format")
    if payload.get("name") != "feedback-aggregation-policy":
        raise PolicyError("Unsupported aggregation policy name")
    try:
        status = PolicyStatus(_required_text(payload, "status"))
    except ValueError as error:
        raise PolicyError("Unsupported aggregation policy status") from error
    schema_ref = _object(payload.get("decision_schema"), "decision_schema")
    if (
        schema_ref.get("name") != schema.name
        or schema_ref.get("version") != schema.version
        or schema_ref.get("sha256") != schema.sha256
    ):
        raise PolicyError("Aggregation policy does not match the loaded decision schema")

    rows = payload.get("questions")
    if not isinstance(rows, list):
        raise PolicyError("Aggregation policy questions must be a list")
    questions: list[QuestionPolicy] = []
    seen: set[str] = set()
    for value in rows:
        row = _object(value, "question policy")
        question_id = _required_text(row, "id")
        if question_id in seen:
            raise PolicyError(f"Duplicate policy question: {question_id}")
        seen.add(question_id)
        spec = schema.question(question_id)
        try:
            primitive = Primitive(_required_text(row, "primitive"))
        except ValueError as error:
            raise PolicyError(f"Unsupported primitive for {question_id}") from error
        if primitive is not spec.primitive:
            raise PolicyError(f"Policy primitive mismatch for {question_id}")
        routing = _required_text(row, "routing")
        expected_routing = "probability_band" if primitive is Primitive.NOUL else "confidence_bands"
        if routing != expected_routing:
            raise PolicyError(f"Invalid routing strategy for {question_id}")
        thresholds = _thresholds(row.get("thresholds"), primitive, question_id)
        questions.append(QuestionPolicy(question_id, primitive, routing, thresholds))

    expected_ids = tuple(question.question_id for question in schema.questions)
    actual_ids = tuple(question.question_id for question in questions)
    if actual_ids != expected_ids:
        raise PolicyError("Policy question ids and order do not match the decision schema")
    calibrated = all(question.thresholds is not None for question in questions)
    calibration = payload.get("calibration")
    if status is PolicyStatus.ACTIVE and (not calibrated or not isinstance(calibration, dict)):
        raise PolicyError("Active policy requires thresholds and calibration provenance")
    if status is PolicyStatus.AWAITING_CALIBRATION and (calibrated or calibration is not None):
        raise PolicyError("Awaiting-calibration policy must not contain fitted thresholds")
    dataset_sha256: str | None = None
    labels_sha256: str | None = None
    if isinstance(calibration, dict):
        dataset_sha256 = _digest(calibration.get("dataset_sha256"), "dataset_sha256")
        labels_sha256 = _digest(calibration.get("labels_sha256"), "labels_sha256")
        _required_text(calibration, "calibrated_at")
    return AggregationPolicy(
        name="feedback-aggregation-policy",
        version=_required_text(payload, "version"),
        status=status,
        decision_schema_version=schema.version,
        decision_schema_sha256=schema.sha256,
        questions=tuple(questions),
        calibration_dataset_sha256=dataset_sha256,
        calibration_labels_sha256=labels_sha256,
        sha256=f"sha256:{hashlib.sha256(source).hexdigest()}",
    )


def _thresholds(value: object, primitive: Primitive, question_id: str) -> Thresholds | None:
    if value is None:
        return None
    row = _object(value, f"{question_id}.thresholds")
    if primitive is Primitive.NOUL:
        if set(row) != {"negative_max", "positive_min"}:
            raise PolicyError(f"Invalid Noul threshold fields for {question_id}")
        negative_max = _probability(row.get("negative_max"), f"{question_id}.negative_max")
        positive_min = _probability(row.get("positive_min"), f"{question_id}.positive_min")
        if negative_max >= positive_min:
            raise PolicyError(f"Noul thresholds overlap for {question_id}")
        return ProbabilityThresholds(negative_max, positive_min)
    if set(row) != {"review_min", "accept_min"}:
        raise PolicyError(f"Invalid confidence threshold fields for {question_id}")
    review_min = _probability(row.get("review_min"), f"{question_id}.review_min")
    accept_min = _probability(row.get("accept_min"), f"{question_id}.accept_min")
    if review_min >= accept_min:
        raise PolicyError(f"Confidence thresholds overlap for {question_id}")
    return ConfidenceThresholds(review_min, accept_min)


def _probability(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise PolicyError(f"{label} must be within [0, 1]")
    return float(value)


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PolicyError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PolicyError(f"{label} must be an object")
    return value


def _required_text(value: dict[str, Any], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise PolicyError(f"Policy field {key} must be non-blank text")
    return raw.strip()
