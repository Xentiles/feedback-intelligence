#!/usr/bin/env python3
"""Build the API demo fixture from the checked-in AI-reference evaluation report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS = {
    "semif": ROOT
    / "evaluation/reports/feedback-decision-1.0.0/semif-qwen3.5-4b-mlx-q4-851bf6e8-vs-sol-ai-reference.json",
    "rules": ROOT
    / "evaluation/reports/feedback-decision-1.0.0/rules-1.0.0-vs-sol-ai-reference.json",
    "llm": ROOT
    / "evaluation/reports/feedback-decision-1.0.0/gpt-5.4-mini-2026-03-17-partial-vs-sol-ai-reference.json",
}
SEMIF_PREDICTIONS = (
    ROOT
    / "evaluation/benchmarks/feedback-decision-1.0.0/semif-qwen3.5-4b-mlx-q4-851bf6e8.predictions.jsonl"
)
EXPERIMENT = (
    ROOT
    / "evaluation/benchmarks/feedback-decision-1.0.0/gpt-5.4-mini-2026-03-17.experiment.json"
)
OUTPUTS = (
    ROOT / "services/api/src/FeedbackIntelligence.Api/Fixtures/evaluation-demo.json",
    ROOT / "contracts/api/examples/demo-evaluation.json",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    reports = {
        name: _object(json.loads(path.read_text(encoding="utf-8")), f"{name} report")
        for name, path in REPORTS.items()
    }
    report = reports["semif"]
    rules_report = reports["rules"]
    llm_report = reports["llm"]
    experiment = _object(
        json.loads(EXPERIMENT.read_text(encoding="utf-8")), "LLM experiment"
    )
    summary = _object(report.get("summary"), "summary")
    engine = _object(report.get("engine"), "engine")
    reference = _object(report.get("reference"), "reference")
    slices = _object(
        _object(report.get("slices"), "slices").get("language"), "language"
    )
    language_slices = []
    for language, raw in sorted(slices.items()):
        value = _object(raw, f"language slice {language}")
        primary = _object(value.get("primary_topic"), f"primary topic {language}")
        language_slices.append(
            {
                "language": language,
                "recordCount": value["record_count"],
                "successCount": value["success_count"],
                "errorCount": value["record_count"] - value["success_count"],
                "primaryTopic": {
                    "macroF1": primary["macro_f1"],
                    "accuracy": primary["accuracy"],
                },
            }
        )
    rule_summary = _object(rules_report.get("summary"), "rule summary")
    rule_engine = _object(rules_report.get("engine"), "rule engine")
    rule_slices = _language_slices(rules_report)
    llm_summary = _object(llm_report.get("summary"), "LLM summary")
    llm_engine = _object(llm_report.get("engine"), "LLM engine")
    llm_slices = _language_slices(llm_report)
    billing = _object(experiment.get("billing_observation"), "billing observation")
    estimate = _object(experiment.get("full_run_cost_estimate"), "cost estimate")
    semif_predictions = [
        _object(json.loads(line), "SemIf prediction")
        for line in SEMIF_PREDICTIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(semif_predictions) != summary["record_count"] or any(
        row.get("status") != "success" for row in semif_predictions
    ):
        raise ValueError("SemIf predictions must contain one successful row per record")
    semif_tokens = sum(
        int(_object(row.get("execution"), "SemIf execution")["input_tokens"])
        + int(_object(row.get("execution"), "SemIf execution")["output_tokens"])
        for row in semif_predictions
    )
    fixture = {
        "kind": "evaluation-comparison",
        "contractVersion": "1.0",
        "context": "demo",
        "availability": {"state": "available", "reason": None},
        "status": "complete",
        "reference": {
            "kind": "ai_reviewed_not_human_gold",
            "model": reference["model"],
            "reasoning": "medium",
        },
        "recordCount": summary["record_count"],
        "successCount": summary["success_count"],
        "errorCount": summary["error_count"],
        "semif": {
            "requestedModel": engine["requested_model"],
            "resolvedModel": engine["resolved_model"],
        },
        "semifPrimaryTopic": {
            "macroF1": summary["primary_topic_macro_f1"],
            "accuracy": summary["primary_topic_accuracy"],
        },
        "semifLanguageSlices": language_slices,
        "rules": {
            "requestedModel": rule_engine["requested_model"],
            "resolvedModel": rule_engine["resolved_model"],
        },
        "rulePrimaryTopic": {
            "macroF1": rule_summary["primary_topic_macro_f1"],
            "accuracy": rule_summary["primary_topic_accuracy"],
        },
        "ruleLanguageSlices": rule_slices,
        "llm": {
            "requestedModel": llm_engine["requested_model"],
            "resolvedModel": llm_engine["resolved_model"],
        },
        "semifCost": {
            "scope": "local_inference",
            "status": "measured_complete",
            "tokens": semif_tokens,
            "costUsd": 0.0,
            "successfulRecords": summary["success_count"],
            "targetRecords": summary["record_count"],
            "estimatedTargetCostUsd": 0.0,
            "estimateMethod": "local_mlx_no_api_charge",
        },
        "llmCost": {
            "scope": "partial_experiment",
            "status": experiment["status"],
            "tokens": billing["tokens"],
            "costUsd": billing["cost_usd"],
            "successfulRecords": experiment["successful_record_count"],
            "targetRecords": experiment["target_record_count"],
            "estimatedTargetCostUsd": estimate["cost_usd"],
            "estimateMethod": "linear_extrapolation_from_owner_reported_partial_spend",
        },
        "llmPrimaryTopic": {
            "macroF1": llm_summary["primary_topic_macro_f1"],
            "accuracy": llm_summary["primary_topic_accuracy"],
        },
        "llmLanguageSlices": llm_slices,
    }
    content = json.dumps(fixture, indent=2, sort_keys=False) + "\n"
    if arguments.check:
        stale = [
            output.relative_to(ROOT)
            for output in OUTPUTS
            if not output.is_file() or output.read_text(encoding="utf-8") != content
        ]
        if stale:
            raise ValueError(f"Evaluation dashboard fixture is stale: {stale}")
        print("Evaluation dashboard fixtures are byte-identical")
        return
    for output in OUTPUTS:
        output.write_text(content, encoding="utf-8")
        print(f"Wrote {output.relative_to(ROOT)}")


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _language_slices(report: dict[str, Any]) -> list[dict[str, Any]]:
    slices = _object(
        _object(report.get("slices"), "slices").get("language"), "language"
    )
    result = []
    for language, raw in sorted(slices.items()):
        value = _object(raw, f"language slice {language}")
        primary = _object(value.get("primary_topic"), f"primary topic {language}")
        result.append(
            {
                "language": language,
                "recordCount": value["record_count"],
                "successCount": value["success_count"],
                "errorCount": value["record_count"] - value["success_count"],
                "primaryTopic": {
                    "macroF1": primary["macro_f1"],
                    "accuracy": primary["accuracy"],
                },
            }
        )
    return result


if __name__ == "__main__":
    main()
