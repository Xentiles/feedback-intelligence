#!/usr/bin/env python3
"""Build selectable dashboard fixtures from complete benchmark predictions."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RECORDS_PATH = ROOT / "evaluation/ai-reference/feedback-decision-1.0.0/records.jsonl"
SOURCE_PATH = ROOT / "data/synthetic/generated/feedback.jsonl"
FIXTURE_DIR = ROOT / "services/api/src/FeedbackIntelligence.Api/Fixtures"
DECISION_NAMESPACE = uuid.UUID("b2fb59c1-b9cc-40ca-8f5c-30da0ba6f755")
METHODS = {
    "semif": {
        "predictions": ROOT
        / "evaluation/benchmarks/feedback-decision-1.0.0/semif-qwen3.5-4b-mlx-q4-851bf6e8.predictions.jsonl",
        "output": FIXTURE_DIR / "dashboard-demo-semif.json",
        "source": {
            "key": "synthetic/feedback-decision-semif/1.0.0",
            "providerId": "synthetic",
            "datasetName": "feedback-decision-semif",
            "datasetVersion": "1.0.0+qwen3.5-4b-mlx-q4",
            "displayName": "SemIf-reviewed synthetic feedback",
            "synthetic": True,
            "modelVersion": "semif-qwen3.5-4b-mlx-q4-851bf6e8",
            "reviewLabel": "SemIf · Qwen3.5-4B · MLX 4-bit",
            "projectionDestination": "demo.semif",
        },
    },
    "rules": {
        "predictions": ROOT
        / "evaluation/benchmarks/feedback-decision-1.0.0/rules-1.0.0.predictions.jsonl",
        "output": FIXTURE_DIR / "dashboard-demo-rules.json",
        "source": {
            "key": "synthetic/feedback-decision-rules/1.0.0",
            "providerId": "synthetic",
            "datasetName": "feedback-decision-rules",
            "datasetVersion": "1.0.0",
            "displayName": "Rules-baseline synthetic feedback",
            "synthetic": True,
            "modelVersion": "rules-1.0.0",
            "reviewLabel": "Deterministic rules baseline",
            "projectionDestination": "demo.rules",
        },
    },
    "sol": {
        "labels": ROOT / "evaluation/ai-reference/feedback-decision-1.0.0/labels.jsonl",
        "output": FIXTURE_DIR / "dashboard-demo.json",
        "source": {
            "key": "synthetic/feedback-decision-ai-reference/1.0.0",
            "providerId": "synthetic",
            "datasetName": "feedback-decision-ai-reference",
            "datasetVersion": "1.0.0+sol-medium",
            "displayName": "Sol-medium reference feedback",
            "synthetic": True,
            "modelVersion": "gpt-5.6-sol/medium",
            "reviewLabel": "Sol medium AI reference · not human gold",
            "projectionDestination": "ai_reference.sol_medium",
        },
    },
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def answer_value(answer: dict[str, Any]) -> Any:
    primitive = answer["type"]
    if primitive == "noul":
        return answer["noul"] >= 0.5
    if primitive == "choice":
        return answer["choice"]
    if primitive == "score":
        return answer["score"]
    raise ValueError(f"Unsupported answer primitive: {primitive}")


def compact_answers(prediction: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        question: {"type": answer["type"], "value": answer_value(answer)}
        for question, answer in prediction["answers"].items()
    }


def final_label_answers(label: dict[str, Any]) -> dict[str, dict[str, Any]]:
    adjudication = label.get("adjudication")
    if adjudication:
        return adjudication["answers"]
    return label["annotations"][0]["answers"]


def value(answers: dict[str, dict[str, Any]], question: str) -> Any:
    return answers[question]["value"]


def derive_signals(answers: dict[str, dict[str, Any]]) -> list[str]:
    topic = value(answers, "primary_topic")
    signals: list[str] = []
    if topic == "delivery" and value(answers, "delivery_experience") <= 1:
        signals.append("delivery_delay")
    if value(answers, "reports_product_defect"):
        signals.append("product_defect")
    if topic == "support" and value(answers, "support_experience") <= 1:
        signals.append("support_friction")
    if topic == "returns_refunds" and value(answers, "resolution_status") in {
        "unresolved",
        "unclear",
    }:
        signals.append("return_unresolved")
    if topic == "website_checkout" and value(answers, "overall_experience") <= 2:
        signals.append("checkout_friction")
    if topic == "compatibility" and value(answers, "product_experience") <= 2:
        signals.append("compatibility_issue")
    return signals


def build_fixture(method: str, configuration: dict[str, Any]) -> dict[str, Any]:
    records = {row["feedback_id"]: row for row in read_jsonl(RECORDS_PATH)}
    source_records = {row["feedback_id"]: row for row in read_jsonl(SOURCE_PATH)}
    if "predictions" in configuration:
        decisions = {
            row["feedback_id"]: compact_answers(row)
            for row in read_jsonl(configuration["predictions"])
            if row["status"] == "success"
        }
    else:
        decisions = {
            row["feedback_id"]: final_label_answers(row)
            for row in read_jsonl(configuration["labels"])
        }
    if records.keys() != decisions.keys():
        raise ValueError(f"{method} decisions do not cover the 480-record sample")
    missing = records.keys() - source_records.keys()
    if missing:
        raise ValueError(
            f"{len(missing)} evaluation records are absent from the source"
        )

    output_records: list[dict[str, Any]] = []
    for feedback_id in sorted(records):
        evaluation_record = records[feedback_id]
        source = source_records[feedback_id]
        answers = decisions[feedback_id]
        products = source.get("related_products") or []
        product = products[0] if products else {}
        topic = value(answers, "primary_topic")
        output_records.append(
            {
                "feedbackId": feedback_id,
                "decisionId": str(
                    uuid.uuid5(
                        DECISION_NAMESPACE,
                        f"{'sol-medium' if method == 'sol' else method}:{feedback_id}",
                    )
                ),
                "occurredAt": source["occurred_at"],
                "sourceRecordId": source["source"]["source_record_id"],
                "channel": evaluation_record["channel"],
                "product": product.get("product_name") or "No related product",
                "category": product.get("category") or "general",
                "language": evaluation_record["language"],
                "title": source.get("title") or topic.replace("_", " ").title(),
                "body": evaluation_record["feedback_text"],
                "topic": topic,
                "signals": derive_signals(answers),
                "answers": answers,
            }
        )

    output_records.sort(key=lambda row: (row["occurredAt"], row["feedbackId"]))
    return {"source": configuration["source"], "records": output_records}


def serialize(fixture: dict[str, Any]) -> str:
    return json.dumps(fixture, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if a committed fixture differs from a fresh build.",
    )
    args = parser.parse_args()
    for method, configuration in METHODS.items():
        output = configuration["output"]
        rendered = serialize(build_fixture(method, configuration))
        if args.check:
            if not output.exists() or output.read_text() != rendered:
                raise SystemExit(f"Dashboard fixture is stale: {output}")
            continue
        output.write_text(rendered)
        print(f"Wrote 480 {method} dashboard records to {output}")
    if args.check:
        print("SemIf, rules, and Sol dashboard fixtures are byte-identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
