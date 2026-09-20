"""Beta-Binomial posterior probability trend candidate."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Literal

from feedback_intelligence_worker.trends.models import (
    DailyObservation,
    DetectionResult,
    DetectorConfig,
    TrendDirection,
    WindowCounts,
)

METHOD_ID = "beta_binomial_probability_of_change"


def detect_beta_binomial_change(
    observations: Iterable[DailyObservation],
    *,
    series_id: str,
    anchor: date,
    config: DetectorConfig,
    expected_direction: Literal["increase", "decrease"],
) -> DetectionResult:
    """Compare independent posterior rate distributions for adjacent windows.

    Each window has a Beta prior and a Binomial likelihood. The exact probability
    that the current rate exceeds the baseline rate is calculated using the finite
    Beta-Beta sum for positive integer posterior shapes.
    """

    if (
        config.beta_prior_alpha is None
        or config.beta_prior_beta is None
        or config.min_probability_of_direction is None
    ):
        raise ValueError(
            "candidate_statistical requires beta priors and min_probability_of_direction"
        )

    current_start = anchor - timedelta(days=config.current_days)
    baseline_start = current_start - timedelta(days=config.baseline_days)
    relevant: dict[date, DailyObservation] = {}
    for observation in observations:
        if observation.series_id != series_id:
            continue
        if not baseline_start <= observation.day < anchor:
            continue
        if observation.day in relevant:
            raise ValueError(f"Duplicate observation for {series_id}/{observation.day}")
        relevant[observation.day] = observation

    expected_days = tuple(
        baseline_start + timedelta(days=offset)
        for offset in range(config.baseline_days + config.current_days)
    )
    snapshot = [
        relevant[day].snapshot_dict()
        if day in relevant
        else {"day": day.isoformat(), "missing": True}
        for day in expected_days
    ]
    snapshot_sha256 = _digest(snapshot)
    evaluation_id = _digest(
        {
            "series_id": series_id,
            "anchor": anchor.isoformat(),
            "expected_direction": expected_direction,
            "method": METHOD_ID,
            "config": config.to_dict(),
            "input_snapshot_sha256": snapshot_sha256,
        }
    )
    current = _counts(relevant, current_start, anchor)
    baseline = _counts(relevant, baseline_start, current_start)

    missing_days = [day for day in expected_days if day not in relevant]
    unknown_days = [
        day for day in expected_days if day in relevant and not relevant[day].coverage_known
    ]
    if missing_days or unknown_days:
        reasons: list[str] = []
        if missing_days:
            reasons.append("missing_days")
        if unknown_days:
            reasons.append("unknown_coverage")
        return DetectionResult(
            evaluation_id=evaluation_id,
            input_snapshot_sha256=snapshot_sha256,
            detector_version=config.version,
            series_id=series_id,
            anchor=anchor,
            status="insufficient_coverage",
            expected_direction=expected_direction,
            direction="flat",
            reasons=tuple(reasons),
            current=current,
            baseline=baseline,
            delta_pp=None,
            ratio=None,
            relative_change_percent=None,
            method=METHOD_ID,
        )

    current_rate = current.rate
    baseline_rate = baseline.rate
    delta_pp = (
        None
        if current_rate is None or baseline_rate is None
        else 100 * (current_rate - baseline_rate)
    )
    direction: TrendDirection
    if delta_pp is None or delta_pp == 0:
        direction = "flat"
    elif delta_pp > 0:
        direction = "increase"
    else:
        direction = "decrease"

    if baseline_rate is None or baseline_rate == 0 or current_rate is None:
        ratio = None
        relative_change_percent = None
    else:
        ratio = current_rate / baseline_rate
        relative_change_percent = 100 * abs(current_rate - baseline_rate) / baseline_rate

    current_alpha = config.beta_prior_alpha + current.accepted_count
    current_beta = config.beta_prior_beta + current.eligible_count - current.accepted_count
    baseline_alpha = config.beta_prior_alpha + baseline.accepted_count
    baseline_beta = config.beta_prior_beta + baseline.eligible_count - baseline.accepted_count
    probability_increase = beta_greater_probability(
        current_alpha,
        current_beta,
        baseline_alpha,
        baseline_beta,
    )
    probability_of_direction = (
        probability_increase if expected_direction == "increase" else 1.0 - probability_increase
    )

    reasons = []
    if current.eligible_count < config.min_current_eligible:
        reasons.append("insufficient_current_eligible")
    if baseline.eligible_count < config.min_baseline_eligible:
        reasons.append("insufficient_baseline_eligible")
    if current.accepted_count < config.min_current_positive:
        reasons.append("insufficient_current_positive")
    if current_rate is None:
        reasons.append("missing_current_rate")
    if baseline_rate is None:
        reasons.append("missing_baseline_rate")
    if delta_pp is not None and abs(delta_pp) < config.min_absolute_delta_pp:
        reasons.append("below_absolute_delta")
    if (
        relative_change_percent is not None
        and relative_change_percent < config.min_relative_change_percent
    ):
        reasons.append("below_relative_change")
    if probability_of_direction < config.min_probability_of_direction:
        reasons.append("below_probability_threshold")
    if direction == "flat":
        reasons.append("no_change")
    elif direction != expected_direction:
        reasons.append("unexpected_direction")

    return DetectionResult(
        evaluation_id=evaluation_id,
        input_snapshot_sha256=snapshot_sha256,
        detector_version=config.version,
        series_id=series_id,
        anchor=anchor,
        status="candidate" if not reasons else "not_candidate",
        expected_direction=expected_direction,
        direction=direction,
        reasons=tuple(reasons),
        current=current,
        baseline=baseline,
        delta_pp=delta_pp,
        ratio=ratio,
        relative_change_percent=relative_change_percent,
        method=METHOD_ID,
        probability_of_direction=probability_of_direction,
    )


def beta_greater_probability(
    left_alpha: int,
    left_beta: int,
    right_alpha: int,
    right_beta: int,
) -> float:
    """Return ``P(Beta(left) > Beta(right))`` without external numerics."""

    if min(left_alpha, left_beta, right_alpha, right_beta) < 1:
        raise ValueError("Beta shapes must be positive integers")
    log_denominator = _log_beta(right_alpha, right_beta)
    log_terms = [
        _log_beta(right_alpha + index, left_beta + right_beta)
        - math.log(left_beta + index)
        - _log_beta(1 + index, left_beta)
        - log_denominator
        for index in range(left_alpha)
    ]
    maximum = max(log_terms)
    probability = math.exp(maximum) * sum(math.exp(term - maximum) for term in log_terms)
    return min(1.0, max(0.0, probability))


def _counts(rows: dict[date, DailyObservation], start: date, end: date) -> WindowCounts:
    selected = [row for day, row in rows.items() if start <= day < end and row.coverage_known]
    return WindowCounts(
        start=start,
        end_exclusive=end,
        accepted_count=sum(row.accepted_count for row in selected),
        eligible_count=sum(row.eligible_count for row in selected),
    )


def _log_beta(alpha: int, beta: int) -> float:
    return math.lgamma(alpha) + math.lgamma(beta) - math.lgamma(alpha + beta)


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
