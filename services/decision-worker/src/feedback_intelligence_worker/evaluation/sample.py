"""Build the deterministic, stratified 480-record annotation sample."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from feedback_intelligence_worker.data.models import FeedbackRecord

SAMPLE_FORMAT = "feedback-evaluation-sample/1.0.0"
SAMPLE_VERSION = "feedback-decision-1.0.0"
SELECTION_SEED = "feedback-evaluation-2026-09-19-v1"
SPLIT_TARGETS = {"development": 300, "calibration": 80, "locked_test": 100}
DOUBLE_PASS_TARGETS = {"development": 75, "calibration": 20, "locked_test": 25}


@dataclass(frozen=True, slots=True)
class Candidate:
    record: FeedbackRecord
    scenario_id: str
    event_id: str | None
    source_type: str
    locale: str
    rank: str
    split: str = ""
    requires_second_pass: bool = False

    @property
    def challenge_class(self) -> str:
        if self.event_id is not None:
            return "event"
        if self.scenario_id in {"ambiguous", "irrelevant_chatter", "mixed_experience"}:
            return "challenge"
        return "standard"

    def record_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SAMPLE_FORMAT,
            "feedback_id": self.record.feedback_id,
            "feedback_text": self.record.original_text,
            "language": self.record.language,
            "channel": self.record.channel,
            "split": self.split,
            "requires_second_pass": self.requires_second_pass,
        }

    def label_template(self) -> dict[str, Any]:
        return {
            "schema_version": "feedback-annotation-record/1.0.0",
            "feedback_id": self.record.feedback_id,
            "split": self.split,
            "requires_second_pass": self.requires_second_pass,
            "annotations": [],
            "adjudication": None,
        }


@dataclass(frozen=True, slots=True)
class EvaluationSample:
    records: tuple[Candidate, ...]
    manifest: dict[str, Any]

    def records_bytes(self) -> bytes:
        return _jsonl(candidate.record_dict() for candidate in self.records)

    def labels_bytes(self) -> bytes:
        return _jsonl(candidate.label_template() for candidate in self.records)

    def manifest_bytes(self) -> bytes:
        return (
            json.dumps(self.manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode()


def build_evaluation_sample(source_dir: Path) -> EvaluationSample:
    manifest_path = source_dir / "seed-manifest.json"
    feedback_path = source_dir / "feedback.jsonl"
    provenance_path = source_dir / "provenance.jsonl"
    manifest = _json_object(manifest_path)
    _verify_sha256(feedback_path, manifest.get("feedback_sha256"), "feedback")
    _verify_sha256(provenance_path, manifest.get("provenance_sha256"), "provenance")
    records = {
        record.feedback_id: record
        for record in (
            FeedbackRecord.from_dict(_json_line(line, feedback_path, number))
            for number, line in enumerate(feedback_path.read_text().splitlines(), start=1)
            if line.strip()
        )
    }
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for number, line in enumerate(provenance_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        row = _json_line(line, provenance_path, number)
        feedback_id = _text(row, "feedback_id")
        if feedback_id in seen or feedback_id not in records:
            raise ValueError(f"Provenance feedback id is duplicate or unknown: {feedback_id}")
        seen.add(feedback_id)
        event = row.get("synthetic_event_id")
        if event is not None and not isinstance(event, str):
            raise ValueError("synthetic_event_id must be text or null")
        candidates.append(
            Candidate(
                record=records[feedback_id],
                scenario_id=_text(row, "scenario_id"),
                event_id=event,
                source_type=_text(row, "source_type"),
                locale=_text(row, "locale"),
                rank=_rank(feedback_id),
            )
        )
    if seen != set(records):
        raise ValueError("Feedback and provenance id sets differ")
    selected = _select(candidates)
    split = _assign_splits(selected)
    finalized = _assign_second_pass(split)
    ordered = tuple(
        sorted(
            finalized,
            key=lambda row: (tuple(SPLIT_TARGETS).index(row.split), row.rank),
        )
    )
    records_bytes = _jsonl(candidate.record_dict() for candidate in ordered)
    labels_bytes = _jsonl(candidate.label_template() for candidate in ordered)
    sample_manifest: dict[str, Any] = {
        "schema_version": "evaluation-selection-manifest/1.0.0",
        "sample_version": SAMPLE_VERSION,
        "selection_seed": SELECTION_SEED,
        "source": {
            "generator_version": manifest.get("generator_version"),
            "seed": manifest.get("seed"),
            "config_sha256": manifest.get("config_sha256"),
            "feedback_sha256": manifest.get("feedback_sha256"),
            "provenance_sha256": manifest.get("provenance_sha256"),
        },
        "record_count": len(ordered),
        "split_counts": _counts(row.split for row in ordered),
        "double_annotated_counts": _counts(
            row.split for row in ordered if row.requires_second_pass
        ),
        "distributions": {
            "languages": _counts(row.locale for row in ordered),
            "sources": _counts(row.source_type for row in ordered),
            "scenarios": _counts(row.scenario_id for row in ordered),
            "events": _counts(row.event_id or "none" for row in ordered),
            "challenge_classes": _counts(row.challenge_class for row in ordered),
        },
        "records_sha256": hashlib.sha256(records_bytes).hexdigest(),
        "labels_template_sha256": hashlib.sha256(labels_bytes).hexdigest(),
        "selection_constraints": {
            "minimum_per_scenario": 10,
            "minimum_per_event": 10,
            "minimum_per_language_source_cell": 12,
        },
        "provenance_usage": "selection_only_never_model_input_or_gold_label",
    }
    return EvaluationSample(ordered, sample_manifest)


def write_evaluation_sample(sample: EvaluationSample, output_dir: Path, *, force: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        output_dir / "records.jsonl": sample.records_bytes(),
        output_dir / "labels.jsonl": sample.labels_bytes(),
        output_dir / "selection-manifest.json": sample.manifest_bytes(),
    }
    existing = [path for path in outputs if path.exists()]
    if existing and not force:
        names = ", ".join(path.name for path in existing)
        raise ValueError(f"Evaluation outputs already exist: {names}")
    for path, content in outputs.items():
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)


def _select(candidates: list[Candidate]) -> list[Candidate]:
    selected: dict[str, Candidate] = {}
    _take_minimum(selected, candidates, lambda row: row.scenario_id, 10)
    event_rows = [row for row in candidates if row.event_id]
    _take_minimum(selected, event_rows, lambda row: row.event_id or "", 10)
    _take_minimum(selected, candidates, lambda row: f"{row.locale}|{row.source_type}", 12)
    for candidate in sorted(candidates, key=lambda row: row.rank):
        if len(selected) == sum(SPLIT_TARGETS.values()):
            break
        selected.setdefault(candidate.record.feedback_id, candidate)
    if len(selected) != sum(SPLIT_TARGETS.values()):
        raise ValueError("Source data cannot satisfy the 480-record evaluation sample")
    return list(selected.values())


def _take_minimum(
    selected: dict[str, Candidate],
    candidates: list[Candidate],
    key: Any,
    minimum: int,
) -> None:
    groups: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        groups[key(candidate)].append(candidate)
    for group_name, rows in sorted(groups.items()):
        if len(rows) < minimum:
            raise ValueError(f"Selection stratum {group_name} has fewer than {minimum} records")
        for candidate in sorted(rows, key=lambda row: row.rank)[:minimum]:
            selected.setdefault(candidate.record.feedback_id, candidate)


def _assign_splits(rows: list[Candidate]) -> list[Candidate]:
    counts = Counter[str]()
    assigned: list[Candidate] = []
    ordered = sorted(
        rows,
        key=lambda row: (row.locale, row.source_type, row.challenge_class, row.rank),
    )
    for row in ordered:
        eligible = [name for name, target in SPLIT_TARGETS.items() if counts[name] < target]
        split = min(eligible, key=lambda name: (counts[name] / SPLIT_TARGETS[name], name))
        counts[split] += 1
        assigned.append(replace(row, split=split))
    if dict(counts) != SPLIT_TARGETS:
        raise ValueError(f"Incorrect evaluation split counts: {dict(counts)}")
    return assigned


def _assign_second_pass(rows: list[Candidate]) -> list[Candidate]:
    selected: set[str] = set()
    for split, target in DOUBLE_PASS_TARGETS.items():
        candidates = sorted(
            (row for row in rows if row.split == split),
            key=lambda row: hashlib.sha256(
                f"second:{SELECTION_SEED}:{row.record.feedback_id}".encode()
            ).hexdigest(),
        )
        selected.update(row.record.feedback_id for row in candidates[:target])
    return [replace(row, requires_second_pass=row.record.feedback_id in selected) for row in rows]


def _rank(feedback_id: str) -> str:
    return hashlib.sha256(f"{SELECTION_SEED}:{feedback_id}".encode()).hexdigest()


def _jsonl(rows: Any) -> bytes:
    return b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for row in rows
    )


def _json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Required source file does not exist: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _json_line(line: str, path: Path, number: int) -> dict[str, Any]:
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object at {path}:{number}")
    return value


def _text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-blank text")
    return value


def _verify_sha256(path: Path, expected: object, label: str) -> None:
    if not path.is_file() or not isinstance(expected, str):
        raise ValueError(f"Missing {label} source or checksum")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"{label} source checksum does not match seed manifest")


def _counts(values: Any) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))
