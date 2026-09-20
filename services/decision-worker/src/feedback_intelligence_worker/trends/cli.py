"""CLI for reproducible planted-incident trend detector back-tests."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from feedback_intelligence_worker.data.config import find_repository_root
from feedback_intelligence_worker.synthetic.spec import GeneratorSpecError, load_generator_spec
from feedback_intelligence_worker.trends.backtest import (
    load_backtest_config,
    report_bytes,
    run_synthetic_backtest,
)
from feedback_intelligence_worker.trends.comparison import (
    compare_reports,
    comparison_bytes,
    load_report,
)
from feedback_intelligence_worker.trends.registry import (
    TrendAlgorithmName,
    get_trend_detector,
    selected_trend_algorithm,
)


def build_parser() -> argparse.ArgumentParser:
    root = find_repository_root()
    parser = argparse.ArgumentParser(
        prog="feedback-trends",
        description="Evaluate a registered trend detector on planted incidents.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    evaluate = subparsers.add_parser("evaluate", help="Run the planted-incident back-test")
    evaluate.add_argument(
        "--config",
        type=Path,
        default=None,
    )
    evaluate.add_argument(
        "--generator-spec",
        type=Path,
        default=root / "data/synthetic/generator-v1.yaml",
    )
    evaluate.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    evaluate.add_argument(
        "--algorithm",
        choices=tuple(algorithm.value for algorithm in TrendAlgorithmName),
    )
    evaluate.add_argument("--json", action="store_true", dest="as_json")
    compare = subparsers.add_parser(
        "compare",
        help="Apply the promotion gate to frozen baseline and candidate reports",
    )
    compare.add_argument(
        "--baseline",
        type=Path,
        default=root / "evaluation/trends/simple-rate-v1.report.json",
    )
    compare.add_argument(
        "--candidate",
        type=Path,
        default=root / "evaluation/trends/candidate-statistical-v1.report.json",
    )
    compare.add_argument(
        "--output",
        type=Path,
        default=root / "evaluation/trends/detector-comparison-v1.report.json",
    )
    compare.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "compare":
            comparison = compare_reports(
                load_report(arguments.baseline),
                load_report(arguments.candidate),
            )
            payload = comparison_bytes(comparison)
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            arguments.output.write_bytes(payload)
            if arguments.as_json:
                sys.stdout.buffer.write(payload)
            else:
                print(f"Wrote {arguments.output}")
                print(
                    f"Decision: {comparison['decision']}; "
                    f"selected={comparison['selected_algorithm']}"
                )
            return 0
        root = find_repository_root()
        algorithm = selected_trend_algorithm(arguments.algorithm or os.getenv("TREND_ALGORITHM"))
        stem = (
            "simple-rate-v1"
            if algorithm is TrendAlgorithmName.SIMPLE_RATE_CHANGE
            else "candidate-statistical-v1"
        )
        config_path = arguments.config or root / f"evaluation/trends/{stem}.config.json"
        output_path = arguments.output or root / f"evaluation/trends/{stem}.report.json"
        config = load_backtest_config(config_path)
        spec = load_generator_spec(arguments.generator_spec)
        report = run_synthetic_backtest(config, spec, get_trend_detector(algorithm))
        payload = report_bytes(report)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(payload)
        if arguments.as_json:
            sys.stdout.buffer.write(payload)
        else:
            metrics = report["metrics"]
            print(f"Wrote {output_path}")
            print(
                f"Detected {metrics['detected_event_count']}/{metrics['event_count']} events; "
                f"precision={metrics['precision']}; recall={metrics['recall']}"
            )
        return 0
    except (GeneratorSpecError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
