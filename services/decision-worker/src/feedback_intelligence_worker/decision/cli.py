"""Run canonical feedback through privacy and a selected decision engine."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from feedback_intelligence_worker.data.config import (
    SUPPORTED_PROVIDERS,
    build_provider,
    find_repository_root,
    selected_provider,
)
from feedback_intelligence_worker.decision.envelope import build_decision_envelope
from feedback_intelligence_worker.decision.recording import write_fixture_set
from feedback_intelligence_worker.decision.registry import (
    DecisionEngineName,
    DecisionEngineSelection,
    create_decision_engine,
)
from feedback_intelligence_worker.decision.schema import load_decision_schema
from feedback_intelligence_worker.privacy import PaymentDataDetectedError, PrivacyBoundary


def build_parser() -> argparse.ArgumentParser:
    root = find_repository_root()
    parser = argparse.ArgumentParser(
        prog="feedback-decisions",
        description="Run redacted feedback through a versioned decision engine.",
    )
    parser.add_argument("provider", nargs="?", choices=SUPPORTED_PROVIDERS)
    parser.add_argument("--path", type=Path)
    parser.add_argument("--file", type=Path)
    parser.add_argument("--mapping", type=Path)
    parser.add_argument(
        "--engine",
        choices=tuple(engine.value for engine in DecisionEngineName),
        default=None,
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=root / "data/fixtures/decisions/demo-semif-qwen3.5-4b-mlx-q4.json",
    )
    parser.add_argument("--schema", type=Path, default=_default_schema(root))
    parser.add_argument("--model")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "data/processed/decisions/decisions.jsonl",
    )
    parser.add_argument("--record-fixture", type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.limit is not None and arguments.limit < 1:
            raise ValueError("--limit must be positive")
        selection = DecisionEngineSelection.from_environment(
            engine=arguments.engine,
            model=arguments.model,
        )
        engine = create_decision_engine(
            selection.engine,
            requested_model=selection.requested_model,
            fixture_path=arguments.fixture,
        )
        schema = load_decision_schema(arguments.schema)
        provider_name = selected_provider(arguments.provider)
        source = build_provider(
            provider_name,
            path=arguments.path,
            file=arguments.file,
            mapping=arguments.mapping,
        ).load_feedback()
        if not source.validation.is_usable:
            raise ValueError("Source dataset has blocking validation errors")
        selected_records = source.records[: arguments.limit]
        boundary = PrivacyBoundary()
        envelopes: list[dict[str, object]] = []
        recordings = []
        rejected_payment_data = 0
        for record in selected_records:
            try:
                state = boundary.prepare_for_decision(record)
            except PaymentDataDetectedError:
                rejected_payment_data += 1
                continue
            result = engine.decide(state, schema)
            envelopes.append(build_decision_envelope(state, schema, result))
            recordings.append((state, result))
        _write_jsonl(arguments.output, envelopes, force=arguments.force)
        if arguments.record_fixture is not None:
            if selection.engine is not DecisionEngineName.SEMIF:
                raise ValueError("Only live SemIf results can be recorded as fixtures")
            write_fixture_set(
                arguments.record_fixture,
                schema=schema,
                recordings=recordings,
                force=arguments.force,
            )
        first_result = None if not recordings else recordings[0][1]
        payload = {
            "provider_id": provider_name,
            "engine": selection.engine.value,
            "schema": schema.identity,
            "schema_sha256": schema.sha256,
            "requested_model": (
                selection.requested_model if first_result is None else first_result.requested_model
            ),
            "resolved_model": (None if first_result is None else first_result.resolved_model),
            "records_selected": len(selected_records),
            "decisions_written": len(envelopes),
            "rejected_payment_data": rejected_payment_data,
            "output": str(arguments.output),
            "fixture_output": (
                None if arguments.record_fixture is None else str(arguments.record_fixture)
            ),
        }
        if arguments.as_json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Wrote {len(envelopes):,} decision envelope(s) to {arguments.output}")
            print(
                f"Engine: {selection.engine.value}; schema: {schema.identity}; "
                f"model: {payload['requested_model']}"
            )
            print("Feedback bodies printed: 0")
        return 1 if rejected_payment_data else 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _default_schema(root: Path) -> Path:
    return root / "schemas/feedback-decision/1.0.0/manifest.json"


def _write_jsonl(path: Path, values: list[dict[str, object]], *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Decision output already exists: {path}; pass --force")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as destination:
            for value in values:
                destination.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
