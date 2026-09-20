"""Synthetic adapter, alert episode, and reproducibility tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from feedback_intelligence_worker.data.config import find_repository_root
from feedback_intelligence_worker.synthetic.generator import SyntheticDatasetGenerator
from feedback_intelligence_worker.synthetic.spec import load_generator_spec
from feedback_intelligence_worker.trends.backtest import (
    AlertEpisode,
    EventTruth,
    build_observations,
    form_alert_episodes,
    load_backtest_config,
    match_episodes,
    report_bytes,
    run_synthetic_backtest,
)
from feedback_intelligence_worker.trends.cli import main
from feedback_intelligence_worker.trends.comparison import (
    compare_reports,
    comparison_bytes,
    load_report,
)
from feedback_intelligence_worker.trends.models import DetectionResult, WindowCounts
from feedback_intelligence_worker.trends.registry import get_trend_detector


def _result(
    day: date,
    *,
    candidate: bool,
    direction: Literal["increase", "decrease", "flat"] = "increase",
) -> DetectionResult:
    window = WindowCounts(day, day, 1, 2)
    return DetectionResult(
        evaluation_id=day.isoformat(),
        input_snapshot_sha256="a" * 64,
        detector_version="test/1",
        series_id="series",
        anchor=day,
        status="candidate" if candidate else "not_candidate",
        expected_direction="increase",
        direction=direction,
        reasons=(),
        current=window,
        baseline=window,
        delta_pp=20,
        ratio=2,
        relative_change_percent=100,
    )


def test_alert_episodes_group_only_consecutive_flagged_days() -> None:
    results = (
        _result(date(2025, 1, 1), candidate=True),
        _result(date(2025, 1, 2), candidate=True),
        _result(date(2025, 1, 3), candidate=False),
        _result(date(2025, 1, 4), candidate=True),
        _result(date(2025, 1, 5), candidate=True, direction="decrease"),
    )
    episodes = form_alert_episodes(results)

    assert [(row.direction, row.start, row.end, row.alert_days) for row in episodes] == [
        ("increase", date(2025, 1, 1), date(2025, 1, 2), 2),
        ("increase", date(2025, 1, 4), date(2025, 1, 4), 1),
        ("decrease", date(2025, 1, 5), date(2025, 1, 5), 1),
    ]


def test_event_matching_is_one_to_one_and_directional() -> None:
    truths = (
        EventTruth("first", "series", "increase", date(2025, 1, 1), date(2025, 1, 4)),
        EventTruth("second", "series", "increase", date(2025, 1, 2), date(2025, 1, 5)),
    )
    episodes = (
        AlertEpisode("series", "decrease", date(2025, 1, 2), date(2025, 1, 2), 1),
        AlertEpisode("series", "increase", date(2025, 1, 3), date(2025, 1, 3), 1),
    )
    matches, unmatched = match_episodes(truths, episodes, grace_days=0)

    assert matches == {"first": 1, "second": None}
    assert unmatched == (0,)


def test_synthetic_adapter_counts_baseline_scenarios_not_only_event_records() -> None:
    root = find_repository_root()
    config = load_backtest_config(root / "evaluation/trends/simple-rate-v1.config.json")
    spec = load_generator_spec(root / "data/synthetic/generator-v1.yaml")
    dataset = SyntheticDatasetGenerator(spec).generate(seed=config.seed, record_count=2_000)
    observations = build_observations(dataset, config.series, spec)
    noise_mapping = next(row for row in config.series if "product_defect_noise" in row.series_id)
    accepted_total = sum(row.accepted_count for row in observations[noise_mapping.series_id])
    provenance_by_id = {row.feedback_id: row for row in dataset.provenance}
    expected = sum(
        1
        for record in dataset.records
        if provenance_by_id[record.feedback_id].scenario_id == "product_defect_noise"
        and any(product.product_id == "GPU-A17" for product in record.related_products)
    )

    assert accepted_total == expected
    assert any(
        row.scenario_id == "product_defect_noise" and row.synthetic_event_id is None
        for row in dataset.provenance
    )
    assert set(observations[noise_mapping.series_id][0].snapshot_dict()) == {
        "day",
        "accepted_count",
        "eligible_count",
        "coverage_known",
    }


def test_frozen_backtest_covers_all_events_and_is_byte_reproducible() -> None:
    root = find_repository_root()
    config = load_backtest_config(root / "evaluation/trends/simple-rate-v1.config.json")
    spec = load_generator_spec(root / "data/synthetic/generator-v1.yaml")

    first = run_synthetic_backtest(config, spec)
    second = run_synthetic_backtest(config, spec)

    assert report_bytes(first) == report_bytes(second)
    assert first["metrics"]["event_count"] == 4
    assert first["metrics"]["detected_event_count"] == 4
    assert {row["event_id"] for row in first["events"]} == {
        "gpu_a17_noise",
        "carrier_delay_winter",
        "support_process_change",
        "returns_backlog",
    }
    assert all(row["matched_evaluation"] is not None for row in first["events"])
    assert all(row["first_evaluation"] is not None for row in first["alert_episodes"])
    assert all(row["first_evaluation"] is not None for row in first["false_alert_episodes"])
    assert first["provenance_boundary"]["truth_fields_withheld_from_detector"] == [
        "scenario_id",
        "synthetic_event_id",
    ]
    assert first["no_incident_sensitivity"]["alert_episode_count"] >= 0
    report_path = root / "evaluation/trends/simple-rate-v1.report.json"
    assert report_path.read_bytes() == report_bytes(first)


def test_cli_writes_the_reproducible_report(tmp_path: Path) -> None:
    root = find_repository_root()
    output = tmp_path / "report.json"

    assert (
        main(
            [
                "evaluate",
                "--config",
                str(root / "evaluation/trends/simple-rate-v1.config.json"),
                "--generator-spec",
                str(root / "data/synthetic/generator-v1.yaml"),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert (
        output.read_bytes() == (root / "evaluation/trends/simple-rate-v1.report.json").read_bytes()
    )


def test_statistical_candidate_backtest_is_reproducible() -> None:
    root = find_repository_root()
    config = load_backtest_config(root / "evaluation/trends/candidate-statistical-v1.config.json")
    spec = load_generator_spec(root / "data/synthetic/generator-v1.yaml")
    detector = get_trend_detector("candidate_statistical")

    first = run_synthetic_backtest(config, spec, detector)
    second = run_synthetic_backtest(config, spec, detector)

    assert report_bytes(first) == report_bytes(second)
    assert first["method"] == "beta_binomial_probability_of_change"
    assert first["metrics"]["event_count"] == 4
    assert all(
        row["first_evaluation"]["probability_of_direction"] >= 0.98
        for row in first["alert_episodes"]
    )
    report_path = root / "evaluation/trends/candidate-statistical-v1.report.json"
    assert report_path.read_bytes() == report_bytes(first)


def test_measured_comparison_retains_simple_detector_when_delay_gate_fails() -> None:
    root = find_repository_root()
    baseline = load_report(root / "evaluation/trends/simple-rate-v1.report.json")
    candidate = load_report(root / "evaluation/trends/candidate-statistical-v1.report.json")

    comparison = compare_reports(baseline, candidate)

    assert comparison["candidate"]["metrics"]["recall"] == 1.0
    assert (
        comparison["candidate"]["metrics"]["precision"]
        > comparison["baseline"]["metrics"]["precision"]
    )
    assert comparison["candidate_promoted"] is False
    assert comparison["selected_algorithm"] == "simple_rate_change"
    failed = [row["name"] for row in comparison["promotion_criteria"] if not row["passed"]]
    assert failed == ["mean_detection_delay_not_higher"]
    report_path = root / "evaluation/trends/detector-comparison-v1.report.json"
    assert report_path.read_bytes() == comparison_bytes(comparison)
