"""Generate a publishable, deterministic status report before gold labels exist."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from feedback_intelligence_worker.decision.schema import DecisionSchema
from feedback_intelligence_worker.evaluation.annotations import validate_annotation_readiness

READINESS_REPORT_FORMAT = "feedback-evaluation-readiness/1.0.0"


def build_readiness_report(
    records_path: Path, labels_path: Path, schema: DecisionSchema
) -> dict[str, Any]:
    readiness = validate_annotation_readiness(records_path, labels_path, schema)
    return {
        "schema_version": READINESS_REPORT_FORMAT,
        "sample_version": "feedback-decision-1.0.0",
        "status": "ready" if readiness.ready_for_calibration else "awaiting_human_labels",
        "readiness": readiness.to_dict(),
        "inputs": {
            "records_sha256": hashlib.sha256(records_path.read_bytes()).hexdigest(),
            "labels_sha256": hashlib.sha256(labels_path.read_bytes()).hexdigest(),
            "decision_schema_sha256": schema.sha256,
        },
        "claims": {
            "gold_dataset_complete": readiness.ready_for_calibration,
            "calibration_allowed": readiness.ready_for_calibration,
            "model_quality_measured": False,
        },
    }


def render_readiness_markdown(report: dict[str, Any]) -> str:
    readiness = report["readiness"]
    lines = [
        "# Gold-set readiness",
        "",
        f"**Status: `{report['status']}`.**",
        "",
        f"Completed records: **{readiness['complete']} / {readiness['total']}**.",
        "",
        "| Split | Complete | Total | Disagreements | Adjudicated | Ready |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for split, value in readiness["splits"].items():
        lines.append(
            f"| `{split}` | {value['complete']} | {value['total']} | "
            f"{value['disagreements']} | {value['adjudicated']} | "
            f"{'yes' if value['ready'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            (
                "The split is frozen; the committed label file remains an annotation template. "
                "No model-quality or calibration claim may be produced until the required "
                "independent passes and adjudications are complete. Locked-test scoring also "
                "requires an explicit unlock flag."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_readiness_report(report: dict[str, Any], output: Path, markdown: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown.write_text(render_readiness_markdown(report), encoding="utf-8")
