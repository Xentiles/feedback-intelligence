"""Validate human annotation structure and report calibration readiness."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from feedback_intelligence_worker.decision.schema import DecisionSchema, Primitive


@dataclass(frozen=True, slots=True)
class AnnotationReadiness:
    total: int
    complete: int
    incomplete: int
    disagreements: int
    adjudicated: int
    ready_for_calibration: bool
    splits: dict[str, dict[str, int | bool]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "complete": self.complete,
            "incomplete": self.incomplete,
            "disagreements": self.disagreements,
            "adjudicated": self.adjudicated,
            "ready_for_calibration": self.ready_for_calibration,
            "splits": self.splits,
        }


def validate_annotation_readiness(
    records_path: Path,
    labels_path: Path,
    schema: DecisionSchema,
) -> AnnotationReadiness:
    records = _read_jsonl(records_path)
    labels = _read_jsonl(labels_path)
    record_by_id = {_text(row, "feedback_id"): row for row in records}
    label_by_id = {_text(row, "feedback_id"): row for row in labels}
    if len(record_by_id) != len(records) or len(label_by_id) != len(labels):
        raise ValueError("Evaluation record and label ids must be unique")
    if set(record_by_id) != set(label_by_id):
        raise ValueError("Evaluation record and label id sets differ")
    complete = disagreements = adjudicated = 0
    split_totals: dict[str, int] = {}
    split_complete: dict[str, int] = {}
    split_disagreements: dict[str, int] = {}
    split_adjudicated: dict[str, int] = {}
    for feedback_id, record in record_by_id.items():
        label = label_by_id[feedback_id]
        if label.get("split") != record.get("split"):
            raise ValueError(f"Split mismatch for {feedback_id}")
        split = _text(record, "split")
        split_totals[split] = split_totals.get(split, 0) + 1
        required_passes = 2 if record.get("requires_second_pass") is True else 1
        annotations = label.get("annotations")
        if not isinstance(annotations, list) or len(annotations) > required_passes:
            raise ValueError(f"Invalid annotation count for {feedback_id}")
        normalized: list[str] = []
        passes: set[int] = set()
        for annotation in annotations:
            if not isinstance(annotation, dict):
                raise ValueError(f"Annotation must be an object for {feedback_id}")
            pass_number = annotation.get("pass")
            if pass_number not in {1, 2} or pass_number in passes:
                raise ValueError(f"Invalid or duplicate annotation pass for {feedback_id}")
            passes.add(pass_number)
            _text(annotation, "annotator_id")
            _text(annotation, "annotated_at")
            answers = _validate_answers(annotation.get("answers"), schema, feedback_id)
            normalized.append(json.dumps(answers, sort_keys=True, separators=(",", ":")))
        has_disagreement = len(normalized) == 2 and normalized[0] != normalized[1]
        adjudication = label.get("adjudication")
        if adjudication is not None:
            if not isinstance(adjudication, dict) or not has_disagreement:
                raise ValueError(f"Adjudication is only valid for a disagreement: {feedback_id}")
            _text(adjudication, "adjudicator_id")
            _text(adjudication, "adjudicated_at")
            _text(adjudication, "reason")
            _validate_answers(adjudication.get("answers"), schema, feedback_id)
            adjudicated += 1
            split_adjudicated[split] = split_adjudicated.get(split, 0) + 1
        if has_disagreement:
            disagreements += 1
            split_disagreements[split] = split_disagreements.get(split, 0) + 1
        is_complete = len(annotations) == required_passes and (
            not has_disagreement or adjudication is not None
        )
        complete += int(is_complete)
        split_complete[split] = split_complete.get(split, 0) + int(is_complete)
    total = len(records)
    splits = {
        split: {
            "total": count,
            "complete": split_complete.get(split, 0),
            "incomplete": count - split_complete.get(split, 0),
            "disagreements": split_disagreements.get(split, 0),
            "adjudicated": split_adjudicated.get(split, 0),
            "ready": split_complete.get(split, 0) == count,
        }
        for split, count in sorted(split_totals.items())
    }
    return AnnotationReadiness(
        total=total,
        complete=complete,
        incomplete=total - complete,
        disagreements=disagreements,
        adjudicated=adjudicated,
        ready_for_calibration=total == 480 and complete == total,
        splits=splits,
    )


def _validate_answers(value: object, schema: DecisionSchema, feedback_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"answers must be an object for {feedback_id}")
    expected = {question.question_id for question in schema.questions}
    if set(value) != expected:
        raise ValueError(f"Answer ids do not match the decision schema for {feedback_id}")
    for question in schema.questions:
        answer = value[question.question_id]
        if not isinstance(answer, dict) or answer.get("type") != question.primitive.value:
            raise ValueError(f"Wrong annotation primitive for {question.question_id}")
        answer_value = answer.get("value")
        if question.primitive is Primitive.CHOICE:
            if answer_value not in {option.option_id for option in question.options}:
                raise ValueError(f"Invalid choice annotation for {question.question_id}")
        elif question.primitive is Primitive.SCORE:
            if isinstance(answer_value, bool) or answer_value not in {
                level.value for level in question.levels
            }:
                raise ValueError(f"Invalid score annotation for {question.question_id}")
        elif not isinstance(answer_value, bool):
            raise ValueError(f"Invalid Noul annotation for {question.question_id}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"JSONL file does not exist: {path}")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Expected JSON object at {path}:{number}")
        rows.append(value)
    return rows


def _text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-blank text")
    return value
