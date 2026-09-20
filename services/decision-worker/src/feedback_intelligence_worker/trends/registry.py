"""Typed trend-algorithm selection and detector registry."""

from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import date
from enum import StrEnum
from typing import Literal, Protocol

from feedback_intelligence_worker.trends.detector import detect_rate_change
from feedback_intelligence_worker.trends.models import (
    DailyObservation,
    DetectionResult,
    DetectorConfig,
)
from feedback_intelligence_worker.trends.statistical import detect_beta_binomial_change


class TrendAlgorithmName(StrEnum):
    SIMPLE_RATE_CHANGE = "simple_rate_change"
    CANDIDATE_STATISTICAL = "candidate_statistical"


class TrendDetector(Protocol):
    def __call__(
        self,
        observations: Iterable[DailyObservation],
        *,
        series_id: str,
        anchor: date,
        config: DetectorConfig,
        expected_direction: Literal["increase", "decrease"],
    ) -> DetectionResult: ...


_TREND_DETECTORS: dict[TrendAlgorithmName, TrendDetector] = {
    TrendAlgorithmName.SIMPLE_RATE_CHANGE: detect_rate_change,
    TrendAlgorithmName.CANDIDATE_STATISTICAL: detect_beta_binomial_change,
}

_TREND_ALGORITHM_ALIASES = {
    "simpleratechange": TrendAlgorithmName.SIMPLE_RATE_CHANGE,
    "candidatestatistical": TrendAlgorithmName.CANDIDATE_STATISTICAL,
}


def selected_trend_algorithm(value: str | None = None) -> TrendAlgorithmName:
    configured = value or os.getenv("TREND_ALGORITHM") or "simple_rate_change"
    try:
        normalized = configured.strip().replace("_", "").replace("-", "").casefold()
        return _TREND_ALGORITHM_ALIASES[normalized]
    except KeyError as error:
        allowed = ", ".join(algorithm.value for algorithm in TrendAlgorithmName)
        raise ValueError(f"TREND_ALGORITHM must be one of: {allowed}") from error


def get_trend_detector(algorithm: TrendAlgorithmName | str) -> TrendDetector:
    selected = (
        algorithm
        if isinstance(algorithm, TrendAlgorithmName)
        else selected_trend_algorithm(algorithm)
    )
    return _TREND_DETECTORS[selected]
