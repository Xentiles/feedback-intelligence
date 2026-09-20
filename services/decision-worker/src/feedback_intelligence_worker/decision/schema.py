"""Load the immutable provider-neutral feedback decision manifest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class DecisionSchemaError(ValueError):
    """Raised when a decision manifest cannot be used safely."""


class Primitive(StrEnum):
    CHOICE = "choice"
    SCORE = "score"
    NOUL = "noul"


@dataclass(frozen=True, slots=True)
class OptionSpec:
    option_id: str
    description: str


@dataclass(frozen=True, slots=True)
class LevelSpec:
    value: int
    label: str
    description: str


@dataclass(frozen=True, slots=True)
class QuestionSpec:
    question_id: str
    primitive: Primitive
    instructions: str
    options: tuple[OptionSpec, ...] = ()
    levels: tuple[LevelSpec, ...] = ()
    true_criteria: str | None = None
    false_criteria: str | None = None


@dataclass(frozen=True, slots=True)
class DecisionSchema:
    name: str
    version: str
    questions: tuple[QuestionSpec, ...]
    allowed_state_fields: tuple[str, ...]
    prohibited_state_fields: tuple[str, ...]
    sha256: str

    @property
    def identity(self) -> str:
        return f"{self.name}/{self.version}"

    def question(self, question_id: str) -> QuestionSpec:
        for question in self.questions:
            if question.question_id == question_id:
                return question
        raise DecisionSchemaError(f"Unknown decision question: {question_id}")


def load_decision_schema(path: Path) -> DecisionSchema:
    if not path.is_file():
        raise DecisionSchemaError(f"Decision manifest does not exist: {path}")
    source = path.read_bytes()
    try:
        payload = json.loads(source)
    except json.JSONDecodeError as error:
        raise DecisionSchemaError(f"Invalid decision manifest JSON: {error}") from error
    if not isinstance(payload, dict):
        raise DecisionSchemaError("Decision manifest must be an object")
    if payload.get("manifest_format") != "feedback-decision-manifest/1.0.0":
        raise DecisionSchemaError("Unsupported decision manifest format")
    if payload.get("name") != "feedback-decision" or payload.get("status") != "active":
        raise DecisionSchemaError("Decision manifest must be the active feedback-decision schema")
    version = _required_text(payload, "version")
    state = _object(payload.get("state"), "state")
    allowed = _text_list(state.get("allowed_fields"), "state.allowed_fields")
    if allowed != ("feedback_text", "language", "channel"):
        raise DecisionSchemaError("Decision state allow-list does not match the privacy boundary")
    prohibited = _text_list(state.get("prohibited_fields"), "state.prohibited_fields")
    rows = payload.get("questions")
    if not isinstance(rows, list) or not rows:
        raise DecisionSchemaError("Decision manifest questions must be a non-empty list")
    questions: list[QuestionSpec] = []
    seen: set[str] = set()
    for value in rows:
        row = _object(value, "question")
        question_id = _required_text(row, "id")
        if question_id in seen:
            raise DecisionSchemaError(f"Duplicate decision question: {question_id}")
        seen.add(question_id)
        try:
            primitive = Primitive(_required_text(row, "primitive"))
        except ValueError as error:
            raise DecisionSchemaError(f"Unsupported primitive for {question_id}") from error
        instructions = _required_text(row, "instructions")
        if primitive is Primitive.CHOICE:
            options = _options(row.get("options"), question_id)
            questions.append(QuestionSpec(question_id, primitive, instructions, options=options))
        elif primitive is Primitive.SCORE:
            levels = _levels(row.get("levels"), question_id)
            questions.append(QuestionSpec(question_id, primitive, instructions, levels=levels))
        else:
            criteria = _object(row.get("criteria"), f"{question_id}.criteria")
            questions.append(
                QuestionSpec(
                    question_id,
                    primitive,
                    instructions,
                    true_criteria=_required_text(criteria, "true"),
                    false_criteria=_required_text(criteria, "false"),
                )
            )
    return DecisionSchema(
        name="feedback-decision",
        version=version,
        questions=tuple(questions),
        allowed_state_fields=allowed,
        prohibited_state_fields=prohibited,
        sha256=f"sha256:{hashlib.sha256(source).hexdigest()}",
    )


def _options(value: object, question_id: str) -> tuple[OptionSpec, ...]:
    if not isinstance(value, list) or len(value) < 2:
        raise DecisionSchemaError(f"Choice {question_id} must define at least two options")
    options: list[OptionSpec] = []
    seen: set[str] = set()
    for value_item in value:
        item = _object(value_item, f"{question_id}.option")
        option_id = _required_text(item, "id")
        if option_id in seen:
            raise DecisionSchemaError(f"Duplicate option {option_id} in {question_id}")
        seen.add(option_id)
        options.append(OptionSpec(option_id, _required_text(item, "description")))
    return tuple(options)


def _levels(value: object, question_id: str) -> tuple[LevelSpec, ...]:
    if not isinstance(value, list) or not 2 <= len(value) <= 10:
        raise DecisionSchemaError(f"Score {question_id} must define two to ten levels")
    levels: list[LevelSpec] = []
    for index, value_item in enumerate(value):
        item = _object(value_item, f"{question_id}.level")
        raw_value = item.get("value")
        if not isinstance(raw_value, int) or isinstance(raw_value, bool) or raw_value != index:
            raise DecisionSchemaError(f"Score {question_id} levels must be consecutive from zero")
        levels.append(
            LevelSpec(
                value=raw_value,
                label=_required_text(item, "label"),
                description=_required_text(item, "description"),
            )
        )
    if len({level.label for level in levels}) != len(levels):
        raise DecisionSchemaError(f"Score {question_id} level labels must be unique")
    return tuple(levels)


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DecisionSchemaError(f"{label} must be an object")
    return value


def _required_text(value: dict[str, Any], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise DecisionSchemaError(f"Decision manifest field {key} must be non-blank text")
    return raw.strip()


def _text_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise DecisionSchemaError(f"{label} must be a non-empty string list")
    cleaned = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(cleaned) != len(value) or len(set(cleaned)) != len(cleaned):
        raise DecisionSchemaError(f"{label} must contain unique non-blank strings")
    return cleaned
