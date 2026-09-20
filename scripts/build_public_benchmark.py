#!/usr/bin/env python3
"""Generate the public benchmark and README table from frozen reports, offline."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = Path("evaluation/reports/feedback-decision-1.0.0")
EXPERIMENT = Path(
    "evaluation/benchmarks/feedback-decision-1.0.0/gpt-5.4-mini-2026-03-17.experiment.json"
)
METHODS = (
    ("SemIf · Qwen3.5-4B", "semif-qwen3.5-4b-mlx-q4-851bf6e8"),
    ("GPT-5.4 Mini", "gpt-5.4-mini-2026-03-17-partial"),
    ("Rules baseline", "rules-1.0.0"),
)
START = "<!-- benchmark:start -->"
END = "<!-- benchmark:end -->"


def build():
    experiment = json.loads((ROOT / EXPERIMENT).read_text())
    rows = []
    sources = {}
    protocol = None
    for label, stem in METHODS:
        path = REPORT_DIR / f"{stem}-vs-sol-ai-reference.json"
        raw = (ROOT / path).read_bytes()
        report = json.loads(raw)
        sources[str(path)] = hashlib.sha256(raw).hexdigest()
        identity = {
            key: report["inputs"][key]
            for key in ("decision_schema_sha256", "labels_sha256", "records_sha256")
        }
        if protocol is not None and protocol != identity:
            raise ValueError("Reports do not share the same corpus, labels and schema")
        protocol = identity
        if report["reference"] != {"kind": "ai_reference", "model": "gpt-5.6-sol"}:
            raise ValueError("Expected the frozen Sol AI reference")
        summary = report["summary"]
        partial = report.get("partial_evaluation", False)
        billing = experiment["billing_observation"] if partial else None
        if partial and (
            summary["success_count"] != experiment["successful_record_count"]
            or sources[str(path)] != experiment["artifacts"]["report_sha256"]
        ):
            raise ValueError("Partial report and closed experiment disagree")
        rows.append(
            {
                "label": label,
                "model": report["engine"]["resolved_model"],
                "status": "closed_partial" if partial else "complete",
                "successful_records": summary["success_count"],
                "target_records": summary.get(
                    "target_record_count", summary["record_count"]
                ),
                "topic_accuracy": summary["primary_topic_accuracy"],
                "topic_macro_f1": summary["primary_topic_macro_f1"],
                "recorded_latency_ms": report["operations"]["latency_ms"],
                "adapter_input_tokens": report["operations"]["input_tokens"],
                "adapter_output_tokens": report["operations"]["output_tokens"],
                "provider_cost_usd": billing["cost_usd"] if billing else 0,
                "cost_basis": billing["source"]
                if billing
                else "local_execution_no_provider_charge_hardware_excluded",
                "owner_reported_tokens": billing["tokens"] if billing else None,
                "estimated_480_record_cost_usd": experiment["full_run_cost_estimate"][
                    "cost_usd"
                ]
                if partial
                else 0,
                "source_report": str(path),
            }
        )
    sources[str(EXPERIMENT)] = hashlib.sha256(
        (ROOT / EXPERIMENT).read_bytes()
    ).hexdigest()
    table = [
        "| Method | Successful / target | Topic accuracy | Topic macro-F1 | Provider cost |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        label = row["label"] + (
            " (closed partial)" if row["status"] == "closed_partial" else ""
        )
        table.append(
            f"| {label} | {row['successful_records']} / {row['target_records']} | "
            f"{row['topic_accuracy']:.2%} | {row['topic_macro_f1']:.4f} | ${row['provider_cost_usd']:.2f} |"
        )
    note = (
        "Agreement with the Sol-medium AI reference on synthetic feedback; **not human gold**. "
        "The 192-record LLM subset is not directly comparable to the complete 480-record runs. "
        "Rules benefit from template repetition. Local costs exclude hardware and electricity; "
        "OpenAI spend is owner-reported. The estimated full LLM run is $"
        f"{experiment['full_run_cost_estimate']['cost_usd']:.2f}, not additional measured spend."
    )
    block = "\n".join(table) + "\n\n" + note
    payload = {
        "schema_version": "public-benchmark/1.0.0",
        "reference_kind": "ai_reference",
        "reference_model": "gpt-5.6-sol",
        "shared_inputs": protocol,
        "methods": rows,
        "source_sha256": sources,
        "limitations": note,
        "latency_note": "Recorded execution telemetry, not a controlled hardware comparison; zero rules latency is timer resolution, not zero execution time.",
    }
    return payload, block


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload, block = build()
    readme = (ROOT / "README.md").read_text()
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise ValueError("README must contain exactly one benchmark marker pair")
    before, rest = readme.split(START)
    _, after = rest.split(END)
    outputs = {
        ROOT / "docs/benchmark.json": json.dumps(
            payload, indent=2, ensure_ascii=False, allow_nan=False
        )
        + "\n",
        ROOT
        / "docs/benchmark.md": "# Recorded AI-reference benchmark\n\nGenerated by `python3 scripts/build_public_benchmark.py`.\n\n"
        + block
        + "\n\nFull precision, model identities, recorded latency, separate token counters, and source hashes are in [benchmark.json](benchmark.json).\n\nRecorded latency comes from different execution environments; it is not a controlled speed comparison. Zero rules latency reflects timer resolution. See the [model card](../MODEL_CARD.md) for scope and limitations.\n",
        ROOT / "README.md": before + START + "\n" + block + "\n" + END + after,
    }
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f"Stale generated content: {path.relative_to(ROOT)}")
        else:
            path.write_text(content)
    print(
        "Public benchmark and README table match frozen artifacts."
        if args.check
        else "Generated public benchmark and README table."
    )


if __name__ == "__main__":
    main()
