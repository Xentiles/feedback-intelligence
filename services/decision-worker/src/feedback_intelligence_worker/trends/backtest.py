"""Reproducible planted-incident back-tests for registered trend detectors."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

from feedback_intelligence_worker.synthetic.generator import (
    GeneratedSyntheticDataset,
    SyntheticDatasetGenerator,
)
from feedback_intelligence_worker.synthetic.spec import GeneratorSpec
from feedback_intelligence_worker.trends.models import (
    DailyObservation,
    DetectionResult,
    DetectorConfig,
)
from feedback_intelligence_worker.trends.registry import TrendDetector, get_trend_detector

REPORT_SCHEMA_VERSION = "trend-backtest-report/1.0.0"


@dataclass(frozen=True, slots=True)
class SeriesMapping:
    series_id: str
    source_type: str
    product_id: str | None
    accepted_scenario_ids: tuple[str, ...]
    expected_direction: Literal["increase", "decrease"]


@dataclass(frozen=True, slots=True)
class EventTruth:
    event_id: str
    series_id: str
    direction: str
    start: date
    end_exclusive: date


@dataclass(frozen=True, slots=True)
class AlertEpisode:
    series_id: str
    direction: str
    start: date
    end: date
    alert_days: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "direction": self.direction,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "alert_days": self.alert_days,
        }


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    schema_version: str
    evaluation_version: str
    seed: int
    record_count: int
    detector: DetectorConfig
    series: tuple[SeriesMapping, ...]
    event_series: dict[str, tuple[str, str]]
    match_grace_days: int
    source_sha256: str


def load_backtest_config(path: Path) -> BacktestConfig:
    source = path.read_bytes()
    value = json.loads(source)
    if not isinstance(value, dict):
        raise ValueError("Trend back-test config must be an object")
    if value.get("schema_version") != "trend-backtest-config/1.0.0":
        raise ValueError("Unsupported trend back-test config schema")
    generator = _object(value.get("synthetic_generator"), "synthetic_generator")
    mappings_value = value.get("series")
    if not isinstance(mappings_value, list) or not mappings_value:
        raise ValueError("series must be a non-empty list")
    series: list[SeriesMapping] = []
    event_series: dict[str, tuple[str, str]] = {}
    seen_series: set[str] = set()
    for raw in mappings_value:
        row = _object(raw, "series item")
        series_id = _text(row, "series_id")
        if series_id in seen_series:
            raise ValueError(f"Duplicate trend series: {series_id}")
        seen_series.add(series_id)
        scenarios = _text_list(row.get("accepted_scenario_ids"), "accepted_scenario_ids")
        product = row.get("product_id")
        if product is not None and (not isinstance(product, str) or not product.strip()):
            raise ValueError("product_id must be non-blank text or null")
        series.append(
            SeriesMapping(
                series_id=series_id,
                source_type=_text(row, "source_type"),
                product_id=product,
                accepted_scenario_ids=scenarios,
                expected_direction=_direction(row, "expected_direction"),
            )
        )
        events = row.get("events")
        if not isinstance(events, list) or not events:
            raise ValueError(f"events must be non-empty for {series_id}")
        for event_raw in events:
            event = _object(event_raw, "event mapping")
            event_id = _text(event, "event_id")
            direction = _text(event, "direction")
            if direction not in {"increase", "decrease"}:
                raise ValueError(f"Unsupported event direction: {direction}")
            if event_id in event_series:
                raise ValueError(f"Duplicate event mapping: {event_id}")
            if direction != series[-1].expected_direction:
                raise ValueError(
                    f"Event {event_id} direction must match its series expected_direction"
                )
            event_series[event_id] = (series_id, direction)
    return BacktestConfig(
        schema_version=str(value["schema_version"]),
        evaluation_version=_text(value, "evaluation_version"),
        seed=_integer(generator, "seed"),
        record_count=_integer(generator, "record_count"),
        detector=DetectorConfig.from_dict(_object(value.get("detector"), "detector")),
        series=tuple(series),
        event_series=event_series,
        match_grace_days=_integer(value, "match_grace_days"),
        source_sha256=hashlib.sha256(source).hexdigest(),
    )


def run_synthetic_backtest(
    config: BacktestConfig,
    generator_spec: GeneratorSpec,
    detector: TrendDetector | None = None,
) -> dict[str, Any]:
    selected_detector = detector or get_trend_detector("simple_rate_change")
    dataset = SyntheticDatasetGenerator(generator_spec).generate(
        seed=config.seed,
        record_count=config.record_count,
    )
    observations = build_observations(dataset, config.series, generator_spec)
    data_end_exclusive = generator_spec.start_date + timedelta(days=generator_spec.day_count)
    first_anchor = generator_spec.start_date + timedelta(
        days=config.detector.baseline_days + config.detector.current_days
    )
    results: list[DetectionResult] = []
    for mapping in config.series:
        series_rows = observations[mapping.series_id]
        for offset in range((data_end_exclusive - first_anchor).days + 1):
            results.append(
                selected_detector(
                    series_rows,
                    series_id=mapping.series_id,
                    anchor=first_anchor + timedelta(days=offset),
                    config=config.detector,
                    expected_direction=mapping.expected_direction,
                )
            )

    episodes = form_alert_episodes(results)
    truths = build_truth(config, generator_spec, data_end_exclusive)
    matches, unmatched_episode_indexes = match_episodes(
        truths,
        episodes,
        grace_days=config.match_grace_days,
    )
    matched_count = sum(match is not None for match in matches.values())
    event_count = len(truths)
    alert_count = len(episodes)
    evaluable_series_days = sum(result.status != "insufficient_coverage" for result in results)
    reason_counts = Counter(reason for result in results for reason in result.reasons)
    status_counts = Counter(result.status for result in results)
    event_rows = []
    detection_delays: list[int] = []
    results_by_series_anchor = {(result.series_id, result.anchor): result for result in results}
    episode_rows = [
        {
            **episode.to_dict(),
            "first_evaluation": results_by_series_anchor[
                (episode.series_id, episode.start)
            ].to_dict(),
        }
        for episode in episodes
    ]
    for truth in truths:
        episode_index = matches[truth.event_id]
        episode = None if episode_index is None else episodes[episode_index]
        matched_evaluation = (
            None
            if episode is None
            else results_by_series_anchor[(episode.series_id, episode.start)].to_dict()
        )
        if episode is not None:
            detection_delays.append((episode.start - truth.start).days)
        event_rows.append(
            {
                "event_id": truth.event_id,
                "series_id": truth.series_id,
                "direction": truth.direction,
                "start": truth.start.isoformat(),
                "end_exclusive": truth.end_exclusive.isoformat(),
                "detected": episode is not None,
                "detection_delay_days": (
                    None if episode is None else (episode.start - truth.start).days
                ),
                "matched_episode": (None if episode_index is None else episode_rows[episode_index]),
                "matched_evaluation": matched_evaluation,
            }
        )

    input_identity = {
        "evaluation_version": config.evaluation_version,
        "config_sha256": config.source_sha256,
        "generator_config_sha256": generator_spec.checksum_sha256,
        "generator_version": generator_spec.generator_version,
        "seed": config.seed,
        "record_count": config.record_count,
        "feedback_sha256": dataset.manifest["feedback_sha256"],
        "provenance_sha256": dataset.manifest["provenance_sha256"],
    }
    method = results[0].method if results else "unknown"
    limitations = [
        "Synthetic scenario attribution substitutes for accepted model outputs.",
        "This report measures one seed and one frozen detector operating point.",
        (
            "The operating point demonstrates planted-event visibility and has not been "
            "selected or validated on independent held-out seeds."
        ),
    ]
    if method == "pooled_binary_rate_change":
        limitations.append(
            "The detector is an effect-size rule and does not provide inferential claims."
        )
    else:
        limitations.extend(
            [
                (
                    "Posterior probability is conditional on the configured independent "
                    "Beta priors and binary-window model."
                ),
                (
                    "The candidate has no multiple-testing correction and is not promoted "
                    "for live use by this report."
                ),
            ]
        )
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "evaluation_id": _digest(input_identity),
        "evaluation_version": config.evaluation_version,
        "method": method,
        "input": input_identity,
        "windows": {
            "anchor_semantics": "UTC T with current [T-7,T) and baseline [T-35,T-7)",
            "first_anchor": first_anchor.isoformat(),
            "last_anchor": data_end_exclusive.isoformat(),
        },
        "detector": config.detector.to_dict(),
        "provenance_boundary": {
            "detector_input_fields": [
                "series_id",
                "day",
                "accepted_count",
                "eligible_count",
                "coverage_known",
            ],
            "truth_fields_withheld_from_detector": ["scenario_id", "synthetic_event_id"],
            "adapter_note": (
                "Scenario provenance maps records to independent binary observations; "
                "event provenance is read only when constructing truth."
            ),
        },
        "coverage": {
            "series_count": len(config.series),
            "evaluated_series_days": len(results),
            "evaluable_series_days": evaluable_series_days,
            "excluded_series_days": len(results) - evaluable_series_days,
            "status_counts": dict(sorted(status_counts.items())),
            "reason_counts": dict(sorted(reason_counts.items())),
        },
        "metrics": {
            "event_count": event_count,
            "detected_event_count": matched_count,
            "recall": _ratio(matched_count, event_count),
            "alert_episode_count": alert_count,
            "matched_alert_episode_count": matched_count,
            "precision": _ratio(matched_count, alert_count),
            "false_alert_episode_count": len(unmatched_episode_indexes),
            "false_alert_episodes_per_100_evaluable_series_days": (
                100 * len(unmatched_episode_indexes) / evaluable_series_days
                if evaluable_series_days
                else None
            ),
            "mean_detection_delay_days": (
                sum(detection_delays) / matched_count if matched_count else None
            ),
        },
        "events": event_rows,
        "alert_episodes": episode_rows,
        "false_alert_episodes": [episode_rows[index] for index in unmatched_episode_indexes],
        "limitations": limitations,
    }
    report["no_incident_sensitivity"] = _no_incident_sensitivity(
        config,
        replace(generator_spec, events=()),
        selected_detector,
    )
    return report


def _no_incident_sensitivity(
    config: BacktestConfig,
    spec: GeneratorSpec,
    detector: TrendDetector,
) -> dict[str, Any]:
    """Measure alerts when the same generator has no planted event rules."""

    dataset = SyntheticDatasetGenerator(spec).generate(
        seed=config.seed,
        record_count=config.record_count,
    )
    observations = build_observations(dataset, config.series, spec)
    data_end_exclusive = spec.start_date + timedelta(days=spec.day_count)
    first_anchor = spec.start_date + timedelta(
        days=config.detector.baseline_days + config.detector.current_days
    )
    results = [
        detector(
            observations[mapping.series_id],
            series_id=mapping.series_id,
            anchor=first_anchor + timedelta(days=offset),
            config=config.detector,
            expected_direction=mapping.expected_direction,
        )
        for mapping in config.series
        for offset in range((data_end_exclusive - first_anchor).days + 1)
    ]
    episodes = form_alert_episodes(results)
    evaluable = sum(result.status != "insufficient_coverage" for result in results)
    return {
        "method": "same_seed_generator_with_events_removed",
        "feedback_sha256": dataset.manifest["feedback_sha256"],
        "evaluable_series_days": evaluable,
        "alert_episode_count": len(episodes),
        "alert_episodes_per_100_evaluable_series_days": (
            100 * len(episodes) / evaluable if evaluable else None
        ),
    }


def build_observations(
    dataset: GeneratedSyntheticDataset,
    mappings: tuple[SeriesMapping, ...],
    spec: GeneratorSpec,
) -> dict[str, tuple[DailyObservation, ...]]:
    """Adapt provenance to binary counts, then discard it before detector calls."""

    provenance_by_id = {row.feedback_id: row for row in dataset.provenance}
    counts: dict[str, dict[date, list[int]]] = {
        mapping.series_id: {
            spec.start_date + timedelta(days=offset): [0, 0] for offset in range(spec.day_count)
        }
        for mapping in mappings
    }
    for record in dataset.records:
        provenance = provenance_by_id[record.feedback_id]
        day = record.occurred_at.date()
        product_ids = {product.product_id for product in record.related_products}
        for mapping in mappings:
            if provenance.source_type != mapping.source_type:
                continue
            if mapping.product_id is not None and mapping.product_id not in product_ids:
                continue
            day_counts = counts[mapping.series_id][day]
            day_counts[1] += 1
            if provenance.scenario_id in mapping.accepted_scenario_ids:
                day_counts[0] += 1
    return {
        mapping.series_id: tuple(
            DailyObservation(
                series_id=mapping.series_id,
                day=day,
                accepted_count=values[0],
                eligible_count=values[1],
            )
            for day, values in sorted(counts[mapping.series_id].items())
        )
        for mapping in mappings
    }


def build_truth(
    config: BacktestConfig,
    spec: GeneratorSpec,
    data_end_exclusive: date,
) -> tuple[EventTruth, ...]:
    spec_events = {event.event_id: event for event in spec.events}
    if set(config.event_series) != set(spec_events):
        missing = sorted(set(spec_events) - set(config.event_series))
        extra = sorted(set(config.event_series) - set(spec_events))
        raise ValueError(
            f"Event mappings must match generator events; missing={missing}, extra={extra}"
        )
    truths = []
    for event_id, (series_id, direction) in sorted(config.event_series.items()):
        event = spec_events[event_id]
        start = spec.start_date + timedelta(days=event.start_day)
        end = (
            data_end_exclusive
            if event.duration_days is None
            else start + timedelta(days=event.duration_days)
        )
        truths.append(EventTruth(event_id, series_id, direction, start, end))
    return tuple(sorted(truths, key=lambda row: (row.start, row.event_id)))


def form_alert_episodes(results: Iterable[DetectionResult]) -> tuple[AlertEpisode, ...]:
    flagged: dict[tuple[str, str], list[date]] = defaultdict(list)
    for result in results:
        if result.is_candidate:
            flagged[(result.series_id, result.direction)].append(result.anchor)
    episodes: list[AlertEpisode] = []
    for (series_id, direction), days in sorted(flagged.items()):
        ordered = sorted(set(days))
        if not ordered:
            continue
        start = previous = ordered[0]
        count = 1
        for day in ordered[1:]:
            if day == previous + timedelta(days=1):
                previous = day
                count += 1
                continue
            episodes.append(AlertEpisode(series_id, direction, start, previous, count))
            start = previous = day
            count = 1
        episodes.append(AlertEpisode(series_id, direction, start, previous, count))
    return tuple(sorted(episodes, key=lambda row: (row.start, row.series_id, row.direction)))


def match_episodes(
    truths: tuple[EventTruth, ...],
    episodes: tuple[AlertEpisode, ...],
    *,
    grace_days: int,
) -> tuple[dict[str, int | None], tuple[int, ...]]:
    """Greedily perform deterministic, one-to-one event/episode matching."""

    if grace_days < 0:
        raise ValueError("grace_days cannot be negative")
    used: set[int] = set()
    matches: dict[str, int | None] = {}
    for truth in sorted(truths, key=lambda row: (row.start, row.event_id)):
        cutoff = truth.end_exclusive + timedelta(days=grace_days)
        candidates = [
            (index, episode)
            for index, episode in enumerate(episodes)
            if index not in used
            and episode.series_id == truth.series_id
            and episode.direction == truth.direction
            and truth.start <= episode.start < cutoff
        ]
        if not candidates:
            matches[truth.event_id] = None
            continue
        index, _ = min(candidates, key=lambda item: (item[1].start, item[0]))
        used.add(index)
        matches[truth.event_id] = index
    return matches, tuple(index for index in range(len(episodes)) if index not in used)


def report_bytes(report: dict[str, Any]) -> bytes:
    return (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


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


def _text_list(value: object, label: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise ValueError(f"{label} must be a non-empty text list")
    return tuple(value)


def _direction(value: dict[str, Any], key: str) -> Literal["increase", "decrease"]:
    direction = _text(value, key)
    if direction == "increase":
        return "increase"
    if direction == "decrease":
        return "decrease"
    raise ValueError(f"{key} must be increase or decrease")
