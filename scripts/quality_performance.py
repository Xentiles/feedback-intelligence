"""Measure repeatable offline quality paths on the frozen 10k synthetic corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from feedback_intelligence_worker.data.cli import _write_import
from feedback_intelligence_worker.data.providers.synthetic import (
    SyntheticDatasetProvider,
)
from feedback_intelligence_worker.privacy import PrivacyBoundary
from feedback_intelligence_worker.privacy.models import (
    PaymentDataDetectedError,
    RedactionKind,
)
from feedback_intelligence_worker.synthetic.generator import (
    SyntheticDatasetGenerator,
    write_generated_dataset,
)
from feedback_intelligence_worker.synthetic.spec import load_generator_spec
from feedback_intelligence_worker.trends.backtest import (
    load_backtest_config,
    report_bytes,
    run_synthetic_backtest,
)
from feedback_intelligence_worker.trends.registry import get_trend_detector

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "data/synthetic/generator-v1.yaml"
SIMPLE_CONFIG = ROOT / "evaluation/trends/simple-rate-v1.config.json"
CANDIDATE_CONFIG = ROOT / "evaluation/trends/candidate-statistical-v1.config.json"
DEFAULT_OUTPUT = ROOT / "docs/quality/performance.json"
SAMPLE_COUNT = 5
RECORD_COUNT = 10_000


def digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def peak_rss() -> tuple[int, int, str]:
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return raw, raw, "bytes"
    return raw, raw * 1024, "kilobytes"


def timed(action: Any) -> dict[str, Any]:
    started = perf_counter()
    details = action()
    elapsed = perf_counter() - started
    raw_rss, rss_bytes, source_unit = peak_rss()
    return {
        "duration_seconds": elapsed,
        "peak_rss_bytes": rss_bytes,
        "peak_rss_raw": raw_rss,
        "peak_rss_source_unit": source_unit,
        **details,
    }


def sample_generate(output: Path) -> dict[str, Any]:
    spec = load_generator_spec(SPEC_PATH)

    def action() -> dict[str, Any]:
        dataset = SyntheticDatasetGenerator(spec).generate(
            seed=spec.default_seed,
            record_count=RECORD_COUNT,
        )
        feedback, provenance, manifest = write_generated_dataset(dataset, output, force=False)
        return {
            "content_sha256": dataset.manifest["feedback_sha256"],
            "record_count": len(dataset.records),
            "seed": spec.default_seed,
            "generator_config_sha256": spec.checksum_sha256,
            "provenance_sha256": dataset.manifest["provenance_sha256"],
            "bytes_written": sum(path.stat().st_size for path in (feedback, provenance, manifest)),
        }

    return timed(action)


def sample_import(source: Path, output: Path) -> dict[str, Any]:
    def action() -> dict[str, Any]:
        result = SyntheticDatasetProvider(source).load_feedback()
        if not result.validation.is_usable:
            raise ValueError("generated synthetic source failed canonical provider validation")
        _write_import(result, output)
        content = output.read_bytes()
        return {
            "content_sha256": digest_bytes(content),
            "records_discovered": result.validation.records_discovered,
            "records_imported": len(result.records),
            "records_rejected": result.validation.rejected_records,
            "bytes_written": output.stat().st_size,
        }

    return timed(action)


def sample_privacy(source: Path) -> dict[str, Any]:
    loaded = SyntheticDatasetProvider(source).load_feedback()
    if not loaded.validation.is_usable:
        raise ValueError("generated synthetic source failed canonical provider validation")

    def action() -> dict[str, Any]:
        boundary = PrivacyBoundary()
        audit_rows: list[dict[str, Any]] = []
        counts: Counter[RedactionKind] = Counter()
        rejected = 0
        for record in loaded.records:
            try:
                prepared = boundary.prepare_for_decision(record)
            except PaymentDataDetectedError:
                rejected += 1
                continue
            counts.update(prepared.redactions.counts)
            audit_rows.append(prepared.to_audit_dict())
        content = (
            json.dumps(audit_rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        ).encode()
        return {
            "content_sha256": digest_bytes(content),
            "records_checked": len(loaded.records),
            "records_prepared": len(audit_rows),
            "payment_records_rejected": rejected,
            "redactions": {
                kind.value: count for kind, count in sorted(counts.items()) if count > 0
            },
        }

    return timed(action)


def sample_trend(config_path: Path, algorithm: str) -> dict[str, Any]:
    config = load_backtest_config(config_path)
    spec = load_generator_spec(SPEC_PATH)

    def action() -> dict[str, Any]:
        report = run_synthetic_backtest(config, spec, get_trend_detector(algorithm))
        content = report_bytes(report)
        metrics = report["metrics"]
        return {
            "content_sha256": digest_bytes(content),
            "record_count": config.record_count,
            "seed": config.seed,
            "config_sha256": config.source_sha256,
            "evaluation_id": report["evaluation_id"],
            "event_count": metrics["event_count"],
            "detected_event_count": metrics["detected_event_count"],
        }

    return timed(action)


def run_child(arguments: argparse.Namespace) -> int:
    if arguments.stage == "generate":
        result = sample_generate(arguments.output)
    elif arguments.stage == "import":
        result = sample_import(arguments.source, arguments.output)
    elif arguments.stage == "privacy":
        result = sample_privacy(arguments.source)
    elif arguments.stage == "trend-simple":
        result = sample_trend(SIMPLE_CONFIG, "simple_rate_change")
    elif arguments.stage == "trend-candidate":
        result = sample_trend(CANDIDATE_CONFIG, "candidate_statistical")
    else:
        raise ValueError(f"unknown stage: {arguments.stage}")
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


def distribution(values: list[float | int]) -> dict[str, float | int]:
    return {
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
    }


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    subsequent = samples[1:]
    return {
        "sample_count": len(samples),
        "first": {
            "duration_seconds": samples[0]["duration_seconds"],
            "peak_rss_bytes": samples[0]["peak_rss_bytes"],
        },
        "subsequent": {
            "sample_count": len(subsequent),
            "duration_seconds": distribution([sample["duration_seconds"] for sample in subsequent]),
            "peak_rss_bytes": distribution([sample["peak_rss_bytes"] for sample in subsequent]),
        },
    }


def run_samples(
    stage: str,
    workspace: Path,
    *,
    source: Path | None = None,
) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    for index in range(SAMPLE_COUNT):
        command = [sys.executable, str(Path(__file__).resolve()), "--sample", stage]
        if source is not None:
            command.extend(("--source", str(source)))
        if stage == "generate":
            command.extend(("--output", str(workspace / f"generated-{index}")))
        elif stage == "import":
            command.extend(("--output", str(workspace / f"import-{index}/feedback.jsonl")))
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        samples.append(json.loads(completed.stdout))
    hashes = {sample["content_sha256"] for sample in samples}
    if len(hashes) != 1:
        raise ValueError(f"{stage} content changed across sequential samples: {sorted(hashes)}")
    return {
        "content_sha256": hashes.pop(),
        "summary": summarize(samples),
        "samples": samples,
    }


def environment() -> dict[str, Any]:
    return {
        "operating_system": platform.system(),
        "operating_system_release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "logical_cpu_count": os.cpu_count(),
        "peak_rss_semantics": (
            "resource.ru_maxrss is bytes on Darwin and kilobytes on Linux; "
            "peak_rss_bytes normalizes either source unit to bytes"
        ),
    }


def build_report() -> dict[str, Any]:
    spec = load_generator_spec(SPEC_PATH)
    with tempfile.TemporaryDirectory(prefix="feedback-performance-") as temporary:
        workspace = Path(temporary)
        stages = {
            "synthetic_generation": run_samples("generate", workspace),
        }
        source = workspace / "generated-0/feedback.jsonl"
        stages["canonical_provider_import"] = run_samples("import", workspace, source=source)
        stages["privacy_transformation"] = run_samples("privacy", workspace, source=source)
        stages["simple_rate_frozen_evaluation"] = run_samples("trend-simple", workspace)
        stages["candidate_statistical_frozen_evaluation"] = run_samples(
            "trend-candidate", workspace
        )
    return {
        "schema_version": "quality-performance-report/1.0.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "environment": environment(),
        "workload": {
            "record_count": RECORD_COUNT,
            "seed": spec.default_seed,
            "generator_config_sha256": spec.checksum_sha256,
            "sequential_samples_per_stage": SAMPLE_COUNT,
            "external_model_calls": 0,
            "database_operations": 0,
            "network_calls": 0,
        },
        "stages": stages,
        "limitations": [
            "This is one local host run over deterministic synthetic data, not an SLA.",
            "Five sequential samples are summarized with min, median, and max; no p95 is claimed.",
            "First/subsequent runs use fresh processes; timings exclude interpreter startup.",
            "OS file caching is not controlled, so the first sample is not a cold-cache guarantee.",
            "Peak RSS is the child process high-water mark and is not an allocation profile.",
            "Provider import includes canonical JSONL validation and temporary file output.",
            "Privacy timing excludes provider loading; it measures local redaction only.",
            "Trend timings include frozen 10k generation and synthetic back-test evaluation.",
            "No database, model, browser, concurrency, or network performance is measured.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--sample",
        dest="stage",
        choices=("generate", "import", "privacy", "trend-simple", "trend-candidate"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--source", type=Path, help=argparse.SUPPRESS)
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    if arguments.stage is not None:
        return run_child(arguments)
    report = build_report()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
