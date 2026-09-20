"""Measured promotion gate for frozen trend detector back-test reports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

COMPARISON_SCHEMA_VERSION = "trend-detector-comparison/1.0.0"


def load_report(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Trend report must be an object: {path}")
    if value.get("schema_version") != "trend-backtest-report/1.0.0":
        raise ValueError(f"Unsupported trend report schema: {path}")
    return value


def compare_reports(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Apply the declared promotion criteria without tuning either report."""

    _require_same_input(baseline, candidate)
    baseline_metrics = _object(baseline, "metrics")
    candidate_metrics = _object(candidate, "metrics")
    baseline_sensitivity = _object(baseline, "no_incident_sensitivity")
    candidate_sensitivity = _object(candidate, "no_incident_sensitivity")
    criteria = [
        _criterion(
            "incident_recall_not_lower",
            ">=",
            _number(baseline_metrics, "recall"),
            _number(candidate_metrics, "recall"),
        ),
        _criterion(
            "episode_precision_higher",
            ">",
            _number(baseline_metrics, "precision"),
            _number(candidate_metrics, "precision"),
        ),
        _criterion(
            "false_episode_rate_lower",
            "<",
            _number(
                baseline_metrics,
                "false_alert_episodes_per_100_evaluable_series_days",
            ),
            _number(
                candidate_metrics,
                "false_alert_episodes_per_100_evaluable_series_days",
            ),
        ),
        _criterion(
            "mean_detection_delay_not_higher",
            "<=",
            _number(baseline_metrics, "mean_detection_delay_days"),
            _number(candidate_metrics, "mean_detection_delay_days"),
        ),
        _criterion(
            "no_incident_episode_rate_lower",
            "<",
            _number(
                baseline_sensitivity,
                "alert_episodes_per_100_evaluable_series_days",
            ),
            _number(
                candidate_sensitivity,
                "alert_episodes_per_100_evaluable_series_days",
            ),
        ),
    ]
    promoted = all(bool(row["passed"]) for row in criteria)
    identity = {
        "baseline_evaluation_id": _text(baseline, "evaluation_id"),
        "candidate_evaluation_id": _text(candidate, "evaluation_id"),
        "criteria": criteria,
    }
    return {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "comparison_id": _digest(identity),
        "input": {
            "seed": _object(baseline, "input")["seed"],
            "record_count": _object(baseline, "input")["record_count"],
            "feedback_sha256": _object(baseline, "input")["feedback_sha256"],
            "generator_config_sha256": _object(baseline, "input")["generator_config_sha256"],
        },
        "baseline": _summary(baseline),
        "candidate": _summary(candidate),
        "promotion_criteria": criteria,
        "candidate_promoted": promoted,
        "selected_algorithm": ("candidate_statistical" if promoted else "simple_rate_change"),
        "decision": ("promote_candidate" if promoted else "retain_simple_rate_change"),
        "limitations": [
            "Both detectors are compared on one shared synthetic seed.",
            "The candidate operating point was explored on this seed and is not held-out.",
            "Promotion requires every declared metric criterion to pass.",
        ],
    }


def comparison_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _require_same_input(baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    baseline_input = _object(baseline, "input")
    candidate_input = _object(candidate, "input")
    for key in (
        "seed",
        "record_count",
        "feedback_sha256",
        "generator_config_sha256",
    ):
        if baseline_input.get(key) != candidate_input.get(key):
            raise ValueError(f"Trend reports do not share input field: {key}")


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    metrics = _object(report, "metrics")
    sensitivity = _object(report, "no_incident_sensitivity")
    return {
        "evaluation_id": _text(report, "evaluation_id"),
        "evaluation_version": _text(report, "evaluation_version"),
        "method": _text(report, "method"),
        "config_sha256": _object(report, "input")["config_sha256"],
        "metrics": {
            "recall": metrics["recall"],
            "precision": metrics["precision"],
            "alert_episode_count": metrics["alert_episode_count"],
            "false_alert_episode_count": metrics["false_alert_episode_count"],
            "false_alert_episodes_per_100_evaluable_series_days": metrics[
                "false_alert_episodes_per_100_evaluable_series_days"
            ],
            "mean_detection_delay_days": metrics["mean_detection_delay_days"],
            "no_incident_alert_episodes_per_100_evaluable_series_days": sensitivity[
                "alert_episodes_per_100_evaluable_series_days"
            ],
        },
    }


def _criterion(
    name: str,
    operator: str,
    baseline: float,
    candidate: float,
) -> dict[str, Any]:
    passed = {
        ">=": candidate >= baseline,
        ">": candidate > baseline,
        "<": candidate < baseline,
        "<=": candidate <= baseline,
    }[operator]
    return {
        "name": name,
        "operator": operator,
        "baseline": baseline,
        "candidate": candidate,
        "passed": passed,
    }


def _object(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"{key} must be an object")
    return item


def _text(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"{key} must be non-blank text")
    return item


def _number(value: dict[str, Any], key: str) -> float:
    item = value.get(key)
    if not isinstance(item, (int, float)) or isinstance(item, bool):
        raise ValueError(f"{key} must be numeric")
    return float(item)


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
