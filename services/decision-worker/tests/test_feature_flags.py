"""Typed runtime feature selection tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from feedback_intelligence_worker.data.config import find_repository_root
from feedback_intelligence_worker.decision.fixture import FixtureDecisionEngine
from feedback_intelligence_worker.decision.llm import LlmSystemOneDecisionEngine
from feedback_intelligence_worker.decision.registry import (
    DecisionEngineName,
    DecisionEngineSelection,
    create_decision_engine,
    parse_decision_engine,
)
from feedback_intelligence_worker.decision.rules import RULE_MODEL, RuleDecisionEngine
from feedback_intelligence_worker.decision.semif import (
    SEMIF_MODEL,
    SemifDecisionEngine,
)
from feedback_intelligence_worker.trends.detector import detect_rate_change
from feedback_intelligence_worker.trends.registry import (
    TrendAlgorithmName,
    get_trend_detector,
    selected_trend_algorithm,
)
from feedback_intelligence_worker.trends.statistical import detect_beta_binomial_change


@pytest.mark.parametrize(
    ("name", "model", "expected_type"),
    [
        (DecisionEngineName.FIXTURE, "recorded-fixture", FixtureDecisionEngine),
        (DecisionEngineName.RULES, RULE_MODEL, RuleDecisionEngine),
        (
            DecisionEngineName.LLM,
            "gpt-5.4-mini-2026-03-17",
            LlmSystemOneDecisionEngine,
        ),
        (DecisionEngineName.SEMIF, SEMIF_MODEL, SemifDecisionEngine),
    ],
)
def test_decision_registry_constructs_every_supported_engine(
    name: DecisionEngineName,
    model: str,
    expected_type: type[object],
) -> None:
    root = find_repository_root()

    engine = create_decision_engine(
        name,
        requested_model=model,
        fixture_path=root / "data/fixtures/decisions/demo-semif-qwen3.5-4b-mlx-q4.json",
    )

    assert isinstance(engine, expected_type)


def test_decision_selection_is_typed_and_reads_model_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "semif")
    monkeypatch.setenv("SEMIF_MODEL", SEMIF_MODEL)

    selection = DecisionEngineSelection.from_environment()

    assert selection == DecisionEngineSelection(
        DecisionEngineName.SEMIF,
        SEMIF_MODEL,
    )


def test_unknown_decision_engine_fails_before_work_is_created() -> None:
    with pytest.raises(ValueError, match="DECISION_ENGINE must be one of"):
        parse_decision_engine("unknown-provider")


@pytest.mark.parametrize("configured", ["simple_rate_change", "SimpleRateChange"])
def test_trend_algorithm_aliases_resolve_to_the_typed_registry(configured: str) -> None:
    algorithm = selected_trend_algorithm(configured)

    assert algorithm is TrendAlgorithmName.SIMPLE_RATE_CHANGE
    assert get_trend_detector(algorithm) is detect_rate_change


@pytest.mark.parametrize("configured", ["candidate_statistical", "CandidateStatistical"])
def test_statistical_algorithm_aliases_resolve_to_the_typed_registry(
    configured: str,
) -> None:
    algorithm = selected_trend_algorithm(configured)

    assert algorithm is TrendAlgorithmName.CANDIDATE_STATISTICAL
    assert get_trend_detector(algorithm) is detect_beta_binomial_change


def test_unknown_trend_algorithm_fails_before_evaluation() -> None:
    with pytest.raises(ValueError, match="TREND_ALGORITHM must be one of"):
        selected_trend_algorithm("magic_detector")


def test_feature_contract_exists_at_the_repository_boundary() -> None:
    root = find_repository_root()
    contract = root / "contracts/config/runtime-features-v1.schema.json"

    assert Path(contract).is_file()
