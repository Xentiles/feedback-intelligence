"""Deterministic pooled-rate trend detector."""

from __future__ import annotations

import hashlib
import json
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


def detect_rate_change(
    observations: Iterable[DailyObservation],
    *,
    series_id: str,
    anchor: date,
    config: DetectorConfig,
    expected_direction: Literal["increase", "decrease"],
) -> DetectionResult:
    """Evaluate the half-open baseline and current windows ending at ``anchor``.

    The caller must state coverage for every UTC day in the combined window. A
    present, known row with zero counts is valid; a missing or unknown day is not.
    Rows outside the combined window are deliberately ignored.
    """

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
    reasons = []
    if current.eligible_count < config.min_current_eligible:
        reasons.append("insufficient_current_eligible")
    if baseline.eligible_count < config.min_baseline_eligible:
        reasons.append("insufficient_baseline_eligible")
    if current.accepted_count < config.min_current_positive:
        reasons.append("insufficient_current_positive")
    if baseline_rate == 0:
        reasons.append("zero_baseline")
    elif baseline_rate is None:
        reasons.append("missing_baseline_rate")
    if current_rate is None:
        reasons.append("missing_current_rate")
    if delta_pp is not None and abs(delta_pp) < config.min_absolute_delta_pp:
        reasons.append("below_absolute_delta")
    if (
        relative_change_percent is not None
        and relative_change_percent < config.min_relative_change_percent
    ):
        reasons.append("below_relative_change")
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
    )


def _counts(rows: dict[date, DailyObservation], start: date, end: date) -> WindowCounts:
    selected = [row for day, row in rows.items() if start <= day < end and row.coverage_known]
    return WindowCounts(
        start=start,
        end_exclusive=end,
        accepted_count=sum(row.accepted_count for row in selected),
        eligible_count=sum(row.eligible_count for row in selected),
    )


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
