"""Boundary and semantics tests for the simple-rate detector."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import Any

import pytest

from feedback_intelligence_worker.trends.detector import detect_rate_change
from feedback_intelligence_worker.trends.models import DailyObservation, DetectorConfig

ANCHOR = date(2026, 1, 5)


def _config(**changes: Any) -> DetectorConfig:
    base = DetectorConfig(
        version="test/1",
        current_days=7,
        baseline_days=28,
        min_current_eligible=10,
        min_baseline_eligible=20,
        min_current_positive=1,
        min_absolute_delta_pp=20,
        min_relative_change_percent=100,
    )
    return replace(base, **changes)


def _rows(
    *,
    baseline_accepted: int,
    baseline_eligible: int,
    current_accepted: int,
    current_eligible: int,
) -> tuple[DailyObservation, ...]:
    start = ANCHOR - timedelta(days=35)
    values: list[DailyObservation] = []
    for offset in range(35):
        accepted = baseline_accepted if offset == 0 else 0
        eligible = baseline_eligible if offset == 0 else 0
        if offset == 28:
            accepted = current_accepted
            eligible = current_eligible
        values.append(
            DailyObservation("series", start + timedelta(days=offset), accepted, eligible)
        )
    return tuple(values)


def test_half_open_windows_pool_counts_and_report_percentage_units() -> None:
    rows = list(
        _rows(
            baseline_accepted=2,
            baseline_eligible=10,
            current_accepted=4,
            current_eligible=10,
        )
    )
    # A large denominator on the last baseline day proves rates are pooled rather
    # than calculated as an unweighted mean of daily rates.
    rows[27] = DailyObservation("series", ANCHOR - timedelta(days=8), 18, 90)
    result = detect_rate_change(
        rows,
        series_id="series",
        anchor=ANCHOR,
        config=_config(min_baseline_eligible=100),
        expected_direction="increase",
    )

    assert result.baseline.accepted_count == 20
    assert result.baseline.eligible_count == 100
    assert result.current.accepted_count == 4
    assert result.current.eligible_count == 10
    assert result.baseline.rate == pytest.approx(0.2)
    assert result.current.rate == pytest.approx(0.4)
    assert result.delta_pp == pytest.approx(20)
    assert result.ratio == pytest.approx(2)
    assert result.relative_change_percent == pytest.approx(100)
    assert result.status == "candidate"  # threshold equality is inclusive


def test_current_start_is_included_and_anchor_is_excluded() -> None:
    rows = list(
        _rows(
            baseline_accepted=2,
            baseline_eligible=10,
            current_accepted=4,
            current_eligible=10,
        )
    )
    rows.append(DailyObservation("series", ANCHOR, 10, 10))
    result = detect_rate_change(
        rows,
        series_id="series",
        anchor=ANCHOR,
        config=_config(min_baseline_eligible=10),
        expected_direction="increase",
    )

    assert result.baseline.eligible_count == 10
    assert result.current.eligible_count == 10


def test_zero_baseline_has_null_ratio_and_never_becomes_candidate() -> None:
    result = detect_rate_change(
        _rows(
            baseline_accepted=0,
            baseline_eligible=20,
            current_accepted=5,
            current_eligible=10,
        ),
        series_id="series",
        anchor=ANCHOR,
        config=_config(),
        expected_direction="increase",
    )

    assert result.ratio is None
    assert result.relative_change_percent is None
    assert result.status == "not_candidate"
    assert "zero_baseline" in result.reasons


def test_minimum_current_positive_support_applies_to_decrease() -> None:
    result = detect_rate_change(
        _rows(
            baseline_accepted=10,
            baseline_eligible=20,
            current_accepted=0,
            current_eligible=10,
        ),
        series_id="series",
        anchor=ANCHOR,
        config=_config(min_current_positive=1),
        expected_direction="decrease",
    )

    assert result.direction == "decrease"
    assert result.status == "not_candidate"
    assert "insufficient_current_positive" in result.reasons


def test_decrease_requires_matching_configured_direction() -> None:
    rows = _rows(
        baseline_accepted=10,
        baseline_eligible=20,
        current_accepted=2,
        current_eligible=10,
    )
    decrease = detect_rate_change(
        rows,
        series_id="series",
        anchor=ANCHOR,
        config=_config(min_absolute_delta_pp=30, min_relative_change_percent=60),
        expected_direction="decrease",
    )
    increase = detect_rate_change(
        rows,
        series_id="series",
        anchor=ANCHOR,
        config=_config(min_absolute_delta_pp=30, min_relative_change_percent=60),
        expected_direction="increase",
    )

    assert decrease.status == "candidate"
    assert decrease.delta_pp == pytest.approx(-30)
    assert decrease.relative_change_percent == pytest.approx(60)
    assert increase.status == "not_candidate"
    assert "unexpected_direction" in increase.reasons


@pytest.mark.parametrize("mode", ["missing", "unknown"])
def test_requires_known_coverage_for_every_day(mode: str) -> None:
    rows = list(
        _rows(
            baseline_accepted=2,
            baseline_eligible=20,
            current_accepted=4,
            current_eligible=10,
        )
    )
    if mode == "missing":
        rows.pop(4)
        expected_reason = "missing_days"
    else:
        original = rows[4]
        rows[4] = replace(original, coverage_known=False)
        expected_reason = "unknown_coverage"

    result = detect_rate_change(
        rows,
        series_id="series",
        anchor=ANCHOR,
        config=_config(),
        expected_direction="increase",
    )

    assert result.status == "insufficient_coverage"
    assert expected_reason in result.reasons


def test_explicit_known_zero_days_are_complete_history() -> None:
    result = detect_rate_change(
        _rows(
            baseline_accepted=2,
            baseline_eligible=20,
            current_accepted=4,
            current_eligible=10,
        ),
        series_id="series",
        anchor=ANCHOR,
        config=_config(),
        expected_direction="increase",
    )
    assert result.status == "candidate"


def test_future_rows_do_not_change_result_or_evaluation_identity() -> None:
    rows = _rows(
        baseline_accepted=2,
        baseline_eligible=20,
        current_accepted=4,
        current_eligible=10,
    )
    first = detect_rate_change(
        rows,
        series_id="series",
        anchor=ANCHOR,
        config=_config(),
        expected_direction="increase",
    )
    second = detect_rate_change(
        (*rows, DailyObservation("series", ANCHOR + timedelta(days=10), 999, 999)),
        series_id="series",
        anchor=ANCHOR,
        config=_config(),
        expected_direction="increase",
    )

    assert first == second
    assert first.evaluation_id == second.evaluation_id
    assert first.input_snapshot_sha256 == second.input_snapshot_sha256
