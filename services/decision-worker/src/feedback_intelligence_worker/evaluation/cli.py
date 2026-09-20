"""Command-line interface for frozen sampling and annotation readiness."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from feedback_intelligence_worker.data.config import find_repository_root
from feedback_intelligence_worker.decision.engine import DecisionEngine
from feedback_intelligence_worker.decision.llm import LLM_MODEL, LlmSystemOneDecisionEngine
from feedback_intelligence_worker.decision.rules import RULE_MODEL, RuleDecisionEngine
from feedback_intelligence_worker.decision.schema import load_decision_schema
from feedback_intelligence_worker.decision.semif import SEMIF_MODEL, SemifDecisionEngine
from feedback_intelligence_worker.evaluation.annotations import validate_annotation_readiness
from feedback_intelligence_worker.evaluation.predict import run_evaluation_predictions
from feedback_intelligence_worker.evaluation.readiness_report import (
    build_readiness_report,
    write_readiness_report,
)
from feedback_intelligence_worker.evaluation.sample import (
    SAMPLE_VERSION,
    build_evaluation_sample,
    write_evaluation_sample,
)
from feedback_intelligence_worker.evaluation.scoring import score_evaluation, write_report


def build_parser() -> argparse.ArgumentParser:
    root = find_repository_root()
    parser = argparse.ArgumentParser(prog="feedback-evaluation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    sample = subparsers.add_parser("sample", help="Build the frozen 480-record sample")
    sample.add_argument("--source", type=Path, default=root / "data/synthetic/generated")
    sample.add_argument(
        "--output", type=Path, default=root / "evaluation/datasets" / SAMPLE_VERSION
    )
    sample.add_argument("--force", action="store_true")
    sample.add_argument("--json", action="store_true", dest="as_json")
    sample.set_defaults(handler=_sample)

    readiness = subparsers.add_parser("readiness", help="Validate labels and calibration gate")
    readiness.add_argument(
        "--dataset", type=Path, default=root / "evaluation/datasets" / SAMPLE_VERSION
    )
    readiness.add_argument(
        "--schema",
        type=Path,
        default=root / "schemas/feedback-decision/1.0.0/manifest.json",
    )
    readiness.add_argument("--json", action="store_true", dest="as_json")
    readiness.set_defaults(handler=_readiness)

    report = subparsers.add_parser(
        "report", help="Write the deterministic gold-set readiness report"
    )
    report.add_argument(
        "--dataset", type=Path, default=root / "evaluation/datasets" / SAMPLE_VERSION
    )
    report.add_argument(
        "--schema",
        type=Path,
        default=root / "schemas/feedback-decision/1.0.0/manifest.json",
    )
    report.add_argument(
        "--output",
        type=Path,
        default=root / "evaluation/reports" / SAMPLE_VERSION / "readiness.json",
    )
    report.add_argument(
        "--markdown",
        type=Path,
        default=root / "evaluation/reports" / SAMPLE_VERSION / "readiness.md",
    )
    report.add_argument("--json", action="store_true", dest="as_json")
    report.set_defaults(handler=_report)

    score = subparsers.add_parser("score", help="Score one complete frozen split")
    score.add_argument("--predictions", type=Path, required=True)
    score.add_argument(
        "--split", choices=("development", "calibration", "locked_test", "all"), required=True
    )
    score.add_argument("--unlock-locked-test", action="store_true")
    score.add_argument(
        "--reference-kind", choices=("human_gold", "ai_reference"), default="human_gold"
    )
    score.add_argument("--reference-model")
    score.add_argument("--allow-partial", action="store_true")
    score.add_argument(
        "--dataset", type=Path, default=root / "evaluation/datasets" / SAMPLE_VERSION
    )
    score.add_argument(
        "--schema",
        type=Path,
        default=root / "schemas/feedback-decision/1.0.0/manifest.json",
    )
    score.add_argument("--output", type=Path, required=True)
    score.add_argument("--markdown", type=Path)
    score.add_argument("--json", action="store_true", dest="as_json")
    score.set_defaults(handler=_score)

    predict = subparsers.add_parser("predict", help="Run a decision engine over evaluation records")
    predict.add_argument(
        "--dataset", type=Path, default=root / "evaluation/datasets" / SAMPLE_VERSION
    )
    predict.add_argument(
        "--schema",
        type=Path,
        default=root / "schemas/feedback-decision/1.0.0/manifest.json",
    )
    predict.add_argument("--engine", choices=("rules", "llm", "semif"), default="semif")
    predict.add_argument("--model")
    predict.add_argument("--output", type=Path, required=True)
    predict.add_argument("--limit", type=int)
    predict.add_argument("--request-delay-seconds", type=float, default=0.0)
    predict.add_argument("--force", action="store_true")
    predict.add_argument("--resume", action="store_true")
    predict.add_argument("--json", action="store_true", dest="as_json")
    predict.set_defaults(handler=_predict)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        return int(arguments.handler(arguments))
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _sample(arguments: argparse.Namespace) -> int:
    sample = build_evaluation_sample(arguments.source)
    write_evaluation_sample(sample, arguments.output, force=arguments.force)
    payload = {
        "sample_version": SAMPLE_VERSION,
        "record_count": len(sample.records),
        "split_counts": sample.manifest["split_counts"],
        "double_annotated_counts": sample.manifest["double_annotated_counts"],
        "records_sha256": sample.manifest["records_sha256"],
        "output": str(arguments.output),
    }
    if arguments.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Wrote {len(sample.records)} frozen evaluation records to {arguments.output}")
    return 0


def _readiness(arguments: argparse.Namespace) -> int:
    schema = load_decision_schema(arguments.schema)
    readiness = validate_annotation_readiness(
        arguments.dataset / "records.jsonl", arguments.dataset / "labels.jsonl", schema
    )
    if arguments.as_json:
        print(json.dumps(readiness.to_dict(), indent=2, sort_keys=True))
    else:
        print(
            f"Annotations: {readiness.complete}/{readiness.total} complete; "
            f"ready_for_calibration={str(readiness.ready_for_calibration).lower()}"
        )
    return 0 if readiness.ready_for_calibration else 1


def _report(arguments: argparse.Namespace) -> int:
    schema = load_decision_schema(arguments.schema)
    report = build_readiness_report(
        arguments.dataset / "records.jsonl", arguments.dataset / "labels.jsonl", schema
    )
    write_readiness_report(report, arguments.output, arguments.markdown)
    if arguments.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Wrote evaluation readiness report to {arguments.output}")
    return 0


def _score(arguments: argparse.Namespace) -> int:
    schema = load_decision_schema(arguments.schema)
    report = score_evaluation(
        records_path=arguments.dataset / "records.jsonl",
        labels_path=arguments.dataset / "labels.jsonl",
        predictions_path=arguments.predictions,
        schema=schema,
        split=arguments.split,
        unlock_locked_test=arguments.unlock_locked_test,
        reference_kind=arguments.reference_kind,
        reference_model=arguments.reference_model,
        allow_partial=arguments.allow_partial,
    )
    write_report(report, arguments.output, arguments.markdown)
    if arguments.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Wrote evaluation report to {arguments.output}")
    return 0


def _predict(arguments: argparse.Namespace) -> int:
    schema = load_decision_schema(arguments.schema)
    defaults = {
        "rules": RULE_MODEL,
        "llm": LLM_MODEL,
        "semif": SEMIF_MODEL,
    }
    model = arguments.model or defaults[arguments.engine]
    engine: DecisionEngine
    if arguments.engine == "rules":
        engine = RuleDecisionEngine(model=model)
    elif arguments.engine == "semif":
        engine = SemifDecisionEngine(model=model)
    else:
        engine = LlmSystemOneDecisionEngine(model=model)
    result = run_evaluation_predictions(
        records_path=arguments.dataset / "records.jsonl",
        output_path=arguments.output,
        schema=schema,
        engine=engine,
        requested_model=model,
        force=arguments.force,
        resume=arguments.resume,
        limit=arguments.limit,
        request_delay_seconds=arguments.request_delay_seconds,
        progress=lambda completed, total: print(
            f"Evaluation predictions: {completed}/{total}", file=sys.stderr, flush=True
        ),
    )
    if arguments.as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            f"Wrote {result['success_count']} successful and {result['error_count']} failed "
            f"prediction(s) to {arguments.output}"
        )
    return 0 if result["error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
