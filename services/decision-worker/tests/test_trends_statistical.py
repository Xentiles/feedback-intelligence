"""Probability and boundary tests for the Beta-Binomial trend candidate."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from feedback_intelligence_worker.trends.models import DailyObservation, DetectorConfig
from feedback_intelligence_worker.trends.statistical import (
    beta_greater_probability,
    detect_beta_binomial_change,
)

ANCHOR = date(2026, 1, 5)


def _config(*, probability: float = 0.95) -> DetectorConfig:
    return DetectorConfig(
        version="beta-binomial/test",
        current_days=7,
        baseline_days=28,
        min_current_eligible=10,
        min_baseline_eligible=20,
        min_current_positive=1,
        min_absolute_delta_pp=10,
        min_relative_change_percent=20,
        beta_prior_alpha=1,
        beta_prior_beta=1,
        min_probability_of_direction=probability,
    )


def _rows(
    *,
    baseline_accepted: int,
    baseline_eligible: int,
    current_accepted: int,
    current_eligible: int,
) -> tuple[DailyObservation, ...]:
    start = ANCHOR - timedelta(days=35)
    rows = [
        DailyObservation("series", start + timedelta(days=offset), 0, 0) for offset in range(35)
    ]
    rows[0] = DailyObservation("series", start, baseline_accepted, baseline_eligible)
    rows[28] = DailyObservation(
        "series",
        start + timedelta(days=28),
        current_accepted,
        current_eligible,
    )
    return tuple(rows)


def test_beta_probability_has_known_uniform_and_symmetry_values() -> None:
    assert beta_greater_probability(1, 1, 1, 1) == pytest.approx(0.5)
    assert beta_greater_probability(2, 1, 1, 1) == pytest.approx(2 / 3)
    forward = beta_greater_probability(8, 4, 3, 9)
    reverse = beta_greater_probability(3, 9, 8, 4)
    assert forward + reverse == pytest.approx(1.0)


def test_statistical_candidate_requires_effect_size_support_and_probability() -> None:
    result = detect_beta_binomial_change(
        _rows(
            baseline_accepted=4,
            baseline_eligible=40,
            current_accepted=8,
            current_eligible=10,
        ),
        series_id="series",
        anchor=ANCHOR,
        config=_config(probability=0.99),
        expected_direction="increase",
    )

    assert result.status == "candidate"
    assert result.method == "beta_binomial_probability_of_change"
    assert result.probability_of_direction is not None
    assert result.probability_of_direction >= 0.99
    assert result.to_dict()["probability_of_direction"] == pytest.approx(
        result.probability_of_direction, abs=5e-11, rel=0
    )


def test_statistical_candidate_reports_probability_gate_failure() -> None:
    result = detect_beta_binomial_change(
        _rows(
            baseline_accepted=10,
            baseline_eligible=40,
            current_accepted=4,
            current_eligible=10,
        ),
        series_id="series",
        anchor=ANCHOR,
        config=_config(probability=0.99),
        expected_direction="increase",
    )

    assert result.status == "not_candidate"
    assert "below_probability_threshold" in result.reasons


def test_statistical_configuration_is_all_or_nothing() -> None:
    with pytest.raises(ValueError, match="must be configured together"):
        DetectorConfig(
            version="invalid",
            current_days=7,
            baseline_days=28,
            min_current_eligible=1,
            min_baseline_eligible=1,
            min_current_positive=1,
            min_absolute_delta_pp=1,
            min_relative_change_percent=1,
            beta_prior_alpha=1,
        )
