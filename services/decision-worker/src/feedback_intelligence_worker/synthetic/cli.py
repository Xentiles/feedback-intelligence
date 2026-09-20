"""CLI for reproducible synthetic dataset generation and verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from feedback_intelligence_worker.data.config import find_repository_root
from feedback_intelligence_worker.synthetic.generator import (
    SyntheticDatasetGenerator,
    write_generated_dataset,
)
from feedback_intelligence_worker.synthetic.spec import GeneratorSpecError, load_generator_spec


def build_parser() -> argparse.ArgumentParser:
    root = find_repository_root()
    parser = argparse.ArgumentParser(
        prog="feedback-synthetic",
        description="Generate and verify deterministic canonical retail feedback.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate canonical JSONL and sidecars")
    _add_paths(generate, root)
    generate.add_argument("--seed", type=int)
    generate.add_argument("--count", type=int)
    generate.add_argument("--force", action="store_true")
    generate.add_argument("--json", action="store_true", dest="as_json")
    generate.set_defaults(handler=_command_generate)

    verify = subparsers.add_parser("verify", help="Regenerate and compare every output byte")
    _add_paths(verify, root)
    verify.add_argument("--json", action="store_true", dest="as_json")
    verify.set_defaults(handler=_command_verify)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        return int(arguments.handler(arguments))
    except (GeneratorSpecError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _add_paths(parser: argparse.ArgumentParser, root: Path) -> None:
    parser.add_argument(
        "--spec",
        type=Path,
        default=root / "data/synthetic/generator-v1.yaml",
        help="Versioned generator YAML",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "data/synthetic/generated",
        help="Directory for generated JSONL and manifest files",
    )


def _command_generate(arguments: argparse.Namespace) -> int:
    spec = load_generator_spec(arguments.spec)
    dataset = SyntheticDatasetGenerator(spec).generate(
        seed=arguments.seed,
        record_count=arguments.count,
    )
    feedback, provenance, manifest = write_generated_dataset(
        dataset,
        arguments.output,
        force=arguments.force,
    )
    payload: dict[str, Any] = {
        "record_count": len(dataset.records),
        "seed": dataset.manifest["seed"],
        "generator_version": dataset.manifest["generator_version"],
        "config_sha256": dataset.manifest["config_sha256"],
        "feedback_sha256": dataset.manifest["feedback_sha256"],
        "provenance_sha256": dataset.manifest["provenance_sha256"],
        "files": {
            "feedback": str(feedback),
            "provenance": str(provenance),
            "manifest": str(manifest),
        },
    }
    if arguments.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Generated {payload['record_count']:,} canonical feedback records.")
        print(f"Seed:       {payload['seed']}")
        print(f"Feedback:   {feedback}")
        print(f"Provenance: {provenance}")
        print(f"Manifest:   {manifest}")
    return 0


def _command_verify(arguments: argparse.Namespace) -> int:
    manifest_path = arguments.output / "seed-manifest.json"
    manifest = _read_manifest(manifest_path)
    seed = _manifest_integer(manifest, "seed", minimum=0)
    count = _manifest_integer(manifest, "record_count", minimum=1)
    spec = load_generator_spec(arguments.spec)
    expected = SyntheticDatasetGenerator(spec).generate(seed=seed, record_count=count)

    paths = {
        "feedback": arguments.output / "feedback.jsonl",
        "provenance": arguments.output / "provenance.jsonl",
        "manifest": manifest_path,
    }
    expected_bytes = {
        "feedback": expected.feedback_bytes(),
        "provenance": expected.provenance_bytes(),
        "manifest": expected.manifest_bytes(),
    }
    mismatches: list[str] = []
    actual_hashes: dict[str, str] = {}
    for name, path in paths.items():
        if not path.is_file():
            mismatches.append(f"missing {path.name}")
            continue
        content = path.read_bytes()
        actual_hashes[name] = hashlib.sha256(content).hexdigest()
        if content != expected_bytes[name]:
            mismatches.append(f"{path.name} differs from deterministic regeneration")

    payload: dict[str, Any] = {
        "verified": not mismatches,
        "seed": seed,
        "record_count": count,
        "generator_version": expected.manifest["generator_version"],
        "config_sha256": spec.checksum_sha256,
        "actual_file_sha256": actual_hashes,
        "mismatches": mismatches,
    }
    if arguments.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    elif mismatches:
        print("Synthetic dataset verification failed:")
        for mismatch in mismatches:
            print(f"  - {mismatch}")
    else:
        print(f"Verified {count:,} records by exact deterministic regeneration.")
        print(f"Seed: {seed}; generator: {expected.manifest['generator_version']}")
    return 1 if mismatches else 0


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Seed manifest does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Seed manifest must contain a JSON object")
    return value


def _manifest_integer(value: dict[str, Any], key: str, *, minimum: int) -> int:
    raw = value.get(key)
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < minimum:
        raise ValueError(f"Seed manifest {key} must be an integer of at least {minimum}")
    return raw


if __name__ == "__main__":
    raise SystemExit(main())
