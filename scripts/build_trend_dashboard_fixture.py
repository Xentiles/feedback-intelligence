#!/usr/bin/env python3
"""Build the dashboard trend fixture from the frozen synthetic back-test report."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "simple_rate_change": (
        ROOT / "evaluation/trends/simple-rate-v1.report.json",
        ROOT / "evaluation/trends/simple-rate-v1.config.json",
        (
            ROOT / "services/api/src/FeedbackIntelligence.Api/Fixtures/trend-demo.json",
            ROOT / "contracts/api/examples/demo-trends.json",
        ),
    ),
    "candidate_statistical": (
        ROOT / "evaluation/trends/candidate-statistical-v1.report.json",
        ROOT / "evaluation/trends/candidate-statistical-v1.config.json",
        (
            ROOT
            / "services/api/src/FeedbackIntelligence.Api/Fixtures/trend-demo-candidate-statistical.json",
            ROOT / "contracts/api/examples/demo-trends-candidate-statistical.json",
        ),
    ),
}

SERIES_PRESENTATION = {
    "product/GPU-A17/topic/product_defect_noise": (
        "product_defect_noise",
        "GPU-A17 noise reports",
        "GPU-A17",
    ),
    "all/topic/delivery_late": ("delivery_late", "Late delivery reports", None),
    "all/topic/support_praise": ("support_praise", "Support praise", None),
    "all/topic/return_unresolved": ("return_unresolved", "Unresolved returns", None),
}

INCIDENT_OUTCOMES = {
    "gpu_a17_noise": "product_defect_noise_increase",
    "carrier_delay_winter": "delivery_delay_increase",
    "support_process_change": "support_praise_increase",
    "returns_backlog": "return_unresolved_increase",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--algorithm",
        choices=tuple(SOURCES),
        default="simple_rate_change",
    )
    arguments = parser.parse_args()
    report_path, config_path, destinations = SOURCES[arguments.algorithm]
    payload = build_fixture(
        _read(report_path),
        _read(config_path),
        arguments.algorithm,
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    stale = [
        path
        for path in destinations
        if not path.is_file() or path.read_text() != rendered
    ]
    if arguments.check:
        if stale:
            raise SystemExit(
                "Trend dashboard fixture is stale: " + ", ".join(map(str, stale))
            )
        print("Trend dashboard fixture matches the frozen back-test report.")
        return
    for path in destinations:
        path.write_text(rendered)
    print(f"Wrote {len(destinations)} measured trend dashboard fixtures.")


def build_fixture(
    report: dict[str, Any],
    config: dict[str, Any],
    algorithm: str = "simple_rate_change",
) -> dict[str, Any]:
    detector = config["detector"]
    series = []
    for row in config["series"]:
        signal_id, label, product = SERIES_PRESENTATION[row["series_id"]]
        series.append(
            {
                "seriesId": row["series_id"],
                "signalId": signal_id,
                "signalLabel": label,
                "product": product,
                "direction": row["expected_direction"],
            }
        )

    results = [
        _result(episode["first_evaluation"], algorithm)
        for episode in report["alert_episodes"]
    ]
    results_by_id = {row["evaluationId"]: row for row in results}
    incidents = []
    for event in report["events"]:
        matched = event["matched_evaluation"]
        matched_id = None if matched is None else matched["evaluation_id"]
        if matched_id is not None and matched_id not in results_by_id:
            raise ValueError(
                f"Matched evaluation is not an alert episode: {matched_id}"
            )
        incidents.append(
            {
                "incidentId": f"synthetic-incident-{event['event_id']}",
                "outcome": INCIDENT_OUTCOMES[event["event_id"]],
                "seriesId": event["series_id"],
                "plantedAt": _midnight(event["start"]),
                "detected": event["detected"],
                "matchedEvaluationId": matched_id,
                "detectionDelayDays": event["detection_delay_days"],
            }
        )

    metrics = report["metrics"]
    delays = [row["detectionDelayDays"] for row in incidents if row["detected"]]
    source_version = (
        f"{report['input']['generator_version']}+seed.{report['input']['seed']}"
        f"+config.{report['input']['generator_config_sha256'][:12]}"
    )
    return {
        "kind": "trend-overview",
        "contractVersion": "1.0",
        "context": "demo",
        "availability": {"state": "available", "reason": None},
        "source": {
            "key": f"synthetic/trend-backtest/seed-{report['input']['seed']}",
            "providerId": "synthetic",
            "datasetName": "Feedback Intelligence deterministic synthetic retail feedback",
            "datasetVersion": source_version,
            "displayName": f"Synthetic detector backtest — seed {report['input']['seed']}",
            "synthetic": True,
        },
        "method": {
            "id": algorithm,
            "version": detector["version"],
            "configurationChecksum": report["input"]["config_sha256"],
            "currentWindowDays": detector["current_days"],
            "baselineWindowDays": detector["baseline_days"],
            "minimumCurrentDenominator": detector["min_current_eligible"],
            "minimumBaselineDenominator": detector["min_baseline_eligible"],
            "minimumCurrentNumerator": detector["min_current_positive"],
            "minimumAbsoluteDeltaPoints": detector["min_absolute_delta_pp"],
            "minimumRelativeChangePercent": detector["min_relative_change_percent"],
            "claim": (
                "posterior_probability_not_multiple_test_adjusted"
                if algorithm == "candidate_statistical"
                else "emerging_signal_not_statistical_significance"
            ),
            "betaPriorAlpha": detector.get("beta_prior_alpha"),
            "betaPriorBeta": detector.get("beta_prior_beta"),
            "minimumProbabilityOfDirection": detector.get(
                "min_probability_of_direction"
            ),
        },
        "summary": {
            "plantedIncidentCount": metrics["event_count"],
            "alertEpisodeCount": metrics["alert_episode_count"],
            "evaluableSeriesDayCount": report["coverage"]["evaluable_series_days"],
            "recall": metrics["recall"],
            "precision": metrics["precision"],
            "medianDetectionDelayDays": statistics.median(delays),
            "falseAlertEpisodesPer100SeriesDays": metrics[
                "false_alert_episodes_per_100_evaluable_series_days"
            ],
        },
        "series": series,
        "results": results,
        "incidents": incidents,
    }


def _result(value: dict[str, Any], algorithm: str) -> dict[str, Any]:
    gates = [
        "current_denominator_met",
        "baseline_denominator_met",
        "current_numerator_met",
        "absolute_delta_met",
        "relative_change_met",
    ]
    if algorithm == "candidate_statistical":
        gates.append("probability_direction_met")
    return {
        "evaluationId": value["evaluation_id"],
        "seriesId": value["series_id"],
        "anchor": _midnight(value["anchor"]),
        "state": "emerging_signal"
        if value["status"] == "candidate"
        else "not_emerging",
        "current": _window(value["current"]),
        "baseline": _window(value["baseline"]),
        "deltaPoints": value["delta_pp"],
        "rateRatio": value["ratio"],
        "relativeChangePercent": value["relative_change_percent"],
        "probabilityOfDirection": value.get("probability_of_direction"),
        "gateReasons": gates,
    }


def _window(value: dict[str, Any]) -> dict[str, Any]:
    rate = value["rate"]
    return {
        "range": {
            "from": _midnight(value["start"]),
            "toExclusive": _midnight(value["end_exclusive"]),
        },
        "numerator": value["accepted_count"],
        "denominator": value["eligible_count"],
        "rate": None if rate is None else rate * 100,
    }


def _midnight(value: str) -> str:
    return f"{value}T00:00:00Z"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected object in {path}")
    return value


if __name__ == "__main__":
    main()
