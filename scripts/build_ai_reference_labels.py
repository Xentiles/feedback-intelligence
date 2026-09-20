#!/usr/bin/env python3
"""Assemble the explicitly non-human Sol reference labels reproducibly."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation/datasets/feedback-decision-1.0.0"
TARGET = ROOT / "evaluation/ai-reference/feedback-decision-1.0.0"
ANNOTATED_AT = "2026-09-19T19:00:00Z"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    records = _jsonl(SOURCE / "records.jsonl")
    pass1 = _by_id(_jsonl(TARGET / "sol-pass1.jsonl"), "Sol pass 1")
    pass2 = _by_id(_jsonl(TARGET / "sol-pass2.jsonl"), "Sol pass 2")
    adjudications = _by_id(_jsonl(TARGET / "sol-adjudications.jsonl"), "adjudications")
    record_ids = [_text(row, "feedback_id") for row in records]
    second_pass_ids = {
        _text(row, "feedback_id") for row in records if row.get("requires_second_pass") is True
    }
    if set(pass1) != set(record_ids):
        raise ValueError("Sol pass 1 must cover all 480 records exactly")
    if set(pass2) != second_pass_ids:
        raise ValueError("Sol pass 2 must cover the 120 second-pass records exactly")

    labels: list[dict[str, Any]] = []
    disagreement_ids: set[str] = set()
    for record in records:
        feedback_id = _text(record, "feedback_id")
        annotations = [_annotation(pass1[feedback_id], expected_pass=1)]
        adjudication: dict[str, Any] | None = None
        if feedback_id in second_pass_ids:
            annotations.append(_annotation(pass2[feedback_id], expected_pass=2))
            if annotations[0]["answers"] != annotations[1]["answers"]:
                disagreement_ids.add(feedback_id)
                source = adjudications.get(feedback_id)
                if source is None:
                    raise ValueError(f"Missing adjudication for {feedback_id}")
                adjudication = {
                    "adjudicator_id": _text(source, "adjudicator_id"),
                    "adjudicated_at": ANNOTATED_AT,
                    "reason": _text(source, "reason"),
                    "answers": _object(source.get("answers"), "adjudication answers"),
                }
        labels.append(
            {
                "schema_version": "feedback-annotation-record/1.0.0",
                "feedback_id": feedback_id,
                "split": _text(record, "split"),
                "requires_second_pass": record.get("requires_second_pass") is True,
                "annotations": annotations,
                "adjudication": adjudication,
            }
        )
    if set(adjudications) != disagreement_ids:
        raise ValueError("Adjudication ids do not exactly match the disagreement set")

    records_bytes = (SOURCE / "records.jsonl").read_bytes()
    labels_bytes = _jsonl_bytes(labels)
    manifest = {
        "schema_version": "feedback-ai-reference-manifest/1.0.0",
        "sample_version": "feedback-decision-1.0.0",
        "reference_kind": "ai_reference",
        "reference_model": "gpt-5.6-sol",
        "reasoning_effort": "medium",
        "record_count": len(records),
        "pass_1_count": len(pass1),
        "pass_2_count": len(pass2),
        "disagreement_record_count": len(disagreement_ids),
        "adjudication_count": len(adjudications),
        "records_sha256": hashlib.sha256(records_bytes).hexdigest(),
        "labels_sha256": hashlib.sha256(labels_bytes).hexdigest(),
        "source_pass_sha256": {
            "pass_1": _sha256(TARGET / "sol-pass1.jsonl"),
            "pass_2": _sha256(TARGET / "sol-pass2.jsonl"),
            "adjudications": _sha256(TARGET / "sol-adjudications.jsonl"),
        },
        "limitations": [
            "AI-reviewed reference; not human gold labels.",
            "Both review passes and adjudication used the same model family.",
            "Suitable for an interim demo comparison, not calibration or release-quality claims.",
        ],
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    expected = {
        TARGET / "records.jsonl": records_bytes,
        TARGET / "labels.jsonl": labels_bytes,
        TARGET / "manifest.json": manifest_bytes,
    }
    if arguments.check:
        stale = [
            str(path.relative_to(ROOT))
            for path, content in expected.items()
            if not path.is_file() or path.read_bytes() != content
        ]
        if stale:
            raise ValueError(f"AI-reference artifacts are stale: {stale}")
        print("AI-reference artifacts are byte-identical")
        return
    TARGET.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE / "records.jsonl", TARGET / "records.jsonl")
    (TARGET / "labels.jsonl").write_bytes(labels_bytes)
    (TARGET / "manifest.json").write_bytes(manifest_bytes)
    print(f"Wrote {len(labels)} AI-reference labels with {len(disagreement_ids)} adjudications")


def _annotation(row: dict[str, Any], *, expected_pass: int) -> dict[str, Any]:
    if row.get("pass") != expected_pass:
        raise ValueError(f"Expected annotation pass {expected_pass}")
    return {
        "annotator_id": _text(row, "annotator_id"),
        "pass": expected_pass,
        "annotated_at": ANNOTATED_AT,
        "answers": _object(row.get("answers"), "annotation answers"),
    }


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"Required JSONL does not exist: {path}")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Expected object at {path}:{number}")
        rows.append(value)
    return rows


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for row in rows
    )


def _by_id(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result = {_text(row, "feedback_id"): row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"{label} contains duplicate feedback ids")
    return result


def _text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-blank text")
    return value


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
