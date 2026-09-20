"""Typed inputs and outputs shared by the trend detectors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

type TrendDirection = Literal["increase", "decrease", "flat"]
type DetectionStatus = Literal["candidate", "not_candidate", "insufficient_coverage"]


@dataclass(frozen=True, slots=True)
class DetectorConfig:
    """Versioned operating point for rate and optional Beta-Binomial detectors."""

    version: str
    current_days: int
    baseline_days: int
    min_current_eligible: int
    min_baseline_eligible: int
    min_current_positive: int
    min_absolute_delta_pp: float
    min_relative_change_percent: float
    beta_prior_alpha: int | None = None
    beta_prior_beta: int | None = None
    min_probability_of_direction: float | None = None

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("Detector version cannot be blank")
        if self.current_days < 1 or self.baseline_days < 1:
            raise ValueError("Detector windows must be positive")
        for label, value in (
            ("min_current_eligible", self.min_current_eligible),
            ("min_baseline_eligible", self.min_baseline_eligible),
            ("min_current_positive", self.min_current_positive),
        ):
            if value < 0:
                raise ValueError(f"{label} cannot be negative")
        for label, number in (
            ("min_absolute_delta_pp", self.min_absolute_delta_pp),
            ("min_relative_change_percent", self.min_relative_change_percent),
        ):
            if number < 0:
                raise ValueError(f"{label} cannot be negative")
        statistical_values = (
            self.beta_prior_alpha,
            self.beta_prior_beta,
            self.min_probability_of_direction,
        )
        if any(value is not None for value in statistical_values) and any(
            value is None for value in statistical_values
        ):
            raise ValueError(
                "beta_prior_alpha, beta_prior_beta, and min_probability_of_direction "
                "must be configured together"
            )
        if self.beta_prior_alpha is not None and self.beta_prior_alpha < 1:
            raise ValueError("beta_prior_alpha must be a positive integer")
        if self.beta_prior_beta is not None and self.beta_prior_beta < 1:
            raise ValueError("beta_prior_beta must be a positive integer")
        if self.min_probability_of_direction is not None and not (
            0.5 < self.min_probability_of_direction < 1
        ):
            raise ValueError("min_probability_of_direction must be between 0.5 and 1")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> DetectorConfig:
        return cls(
            version=_text(value, "version"),
            current_days=_integer(value, "current_days"),
            baseline_days=_integer(value, "baseline_days"),
            min_current_eligible=_integer(value, "min_current_eligible"),
            min_baseline_eligible=_integer(value, "min_baseline_eligible"),
            min_current_positive=_integer(value, "min_current_positive"),
            min_absolute_delta_pp=_number(value, "min_absolute_delta_pp"),
            min_relative_change_percent=_number(value, "min_relative_change_percent"),
            beta_prior_alpha=_optional_integer(value, "beta_prior_alpha"),
            beta_prior_beta=_optional_integer(value, "beta_prior_beta"),
            min_probability_of_direction=_optional_number(value, "min_probability_of_direction"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "version": self.version,
            "current_days": self.current_days,
            "baseline_days": self.baseline_days,
            "min_current_eligible": self.min_current_eligible,
            "min_baseline_eligible": self.min_baseline_eligible,
            "min_current_positive": self.min_current_positive,
            "min_absolute_delta_pp": self.min_absolute_delta_pp,
            "min_relative_change_percent": self.min_relative_change_percent,
        }
        if self.beta_prior_alpha is not None:
            payload["beta_prior_alpha"] = self.beta_prior_alpha
            payload["beta_prior_beta"] = self.beta_prior_beta
            payload["min_probability_of_direction"] = self.min_probability_of_direction
        return payload


@dataclass(frozen=True, slots=True)
class DailyObservation:
    """One known or explicitly unknown UTC calendar-day aggregate."""

    series_id: str
    day: date
    accepted_count: int
    eligible_count: int
    coverage_known: bool = True

    def __post_init__(self) -> None:
        if not self.series_id.strip():
            raise ValueError("Series id cannot be blank")
        if self.accepted_count < 0 or self.eligible_count < 0:
            raise ValueError("Observation counts cannot be negative")
        if self.accepted_count > self.eligible_count:
            raise ValueError("Accepted count cannot exceed eligible count")

    def snapshot_dict(self) -> dict[str, Any]:
        return {
            "day": self.day.isoformat(),
            "accepted_count": self.accepted_count,
            "eligible_count": self.eligible_count,
            "coverage_known": self.coverage_known,
        }


@dataclass(frozen=True, slots=True)
class WindowCounts:
    start: date
    end_exclusive: date
    accepted_count: int
    eligible_count: int

    @property
    def rate(self) -> float | None:
        if self.eligible_count == 0:
            return None
        return self.accepted_count / self.eligible_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "end_exclusive": self.end_exclusive.isoformat(),
            "accepted_count": self.accepted_count,
            "eligible_count": self.eligible_count,
            "rate": self.rate,
        }


@dataclass(frozen=True, slots=True)
class DetectionResult:
    evaluation_id: str
    input_snapshot_sha256: str
    detector_version: str
    series_id: str
    anchor: date
    status: DetectionStatus
    expected_direction: Literal["increase", "decrease"]
    direction: TrendDirection
    reasons: tuple[str, ...]
    current: WindowCounts
    baseline: WindowCounts
    delta_pp: float | None
    ratio: float | None
    relative_change_percent: float | None
    method: str = "pooled_binary_rate_change"
    probability_of_direction: float | None = None

    @property
    def is_candidate(self) -> bool:
        return self.status == "candidate"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "evaluation_id": self.evaluation_id,
            "input_snapshot_sha256": self.input_snapshot_sha256,
            "detector_version": self.detector_version,
            "method": self.method,
            "series_id": self.series_id,
            "anchor": self.anchor.isoformat(),
            "status": self.status,
            "expected_direction": self.expected_direction,
            "direction": self.direction,
            "reasons": list(self.reasons),
            "current": self.current.to_dict(),
            "baseline": self.baseline.to_dict(),
            "delta_pp": self.delta_pp,
            "ratio": self.ratio,
            "relative_change_percent": self.relative_change_percent,
        }
        if self.probability_of_direction is not None:
            # libm lgamma varies slightly across operating systems. Keep reports
            # stable at ten decimal places; decision gates use the unrounded value.
            payload["probability_of_direction"] = round(self.probability_of_direction, 10)
        return payload


def _text(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} must be non-blank text")
    return item


def _integer(value: dict[str, Any], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise ValueError(f"{key} must be an integer")
    return item


def _number(value: dict[str, Any], key: str) -> float:
    item = value.get(key)
    if not isinstance(item, (int, float)) or isinstance(item, bool):
        raise ValueError(f"{key} must be a number")
    return float(item)


def _optional_integer(value: dict[str, Any], key: str) -> int | None:
    if key not in value:
        return None
    return _integer(value, key)


def _optional_number(value: dict[str, Any], key: str) -> float | None:
    if key not in value:
        return None
    return _number(value, key)
