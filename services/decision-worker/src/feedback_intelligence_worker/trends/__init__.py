"""Transparent rate-normalised and statistical trend detection."""

from feedback_intelligence_worker.trends.detector import detect_rate_change
from feedback_intelligence_worker.trends.models import (
    DailyObservation,
    DetectionResult,
    DetectorConfig,
)
from feedback_intelligence_worker.trends.registry import (
    TrendAlgorithmName,
    get_trend_detector,
    selected_trend_algorithm,
)
from feedback_intelligence_worker.trends.statistical import (
    beta_greater_probability,
    detect_beta_binomial_change,
)

__all__ = [
    "DailyObservation",
    "DetectionResult",
    "DetectorConfig",
    "TrendAlgorithmName",
    "beta_greater_probability",
    "detect_beta_binomial_change",
    "detect_rate_change",
    "get_trend_detector",
    "selected_trend_algorithm",
]
