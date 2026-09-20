"""Typed decision-engine selection and construction."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from feedback_intelligence_worker.decision.engine import DecisionEngine
from feedback_intelligence_worker.decision.fixture import FixtureDecisionEngine
from feedback_intelligence_worker.decision.llm import LLM_MODEL, LlmSystemOneDecisionEngine
from feedback_intelligence_worker.decision.rules import RULE_MODEL, RuleDecisionEngine
from feedback_intelligence_worker.decision.semif import SEMIF_MODEL, SemifDecisionEngine


class DecisionEngineName(StrEnum):
    FIXTURE = "fixture"
    RULES = "rules"
    LLM = "llm"
    SEMIF = "semif"


@dataclass(frozen=True, slots=True)
class DecisionEngineSelection:
    engine: DecisionEngineName
    requested_model: str

    @classmethod
    def from_environment(
        cls,
        *,
        engine: str | None = None,
        model: str | None = None,
    ) -> DecisionEngineSelection:
        selected = parse_decision_engine(engine or os.getenv("DECISION_ENGINE") or "fixture")
        if model is not None:
            requested_model = model
        else:
            environment_name = _MODEL_ENVIRONMENTS[selected]
            configured = None if environment_name is None else os.getenv(environment_name)
            requested_model = configured or _DEFAULT_MODELS[selected]
        return cls(selected, requested_model)


EngineBuilder = Callable[[str, Path], DecisionEngine]


def _fixture_engine(_requested_model: str, fixture_path: Path) -> DecisionEngine:
    return FixtureDecisionEngine(fixture_path)


def _rules_engine(requested_model: str, _fixture_path: Path) -> DecisionEngine:
    return RuleDecisionEngine(model=requested_model)


def _llm_engine(requested_model: str, _fixture_path: Path) -> DecisionEngine:
    return LlmSystemOneDecisionEngine(model=requested_model)


def _semif_engine(requested_model: str, _fixture_path: Path) -> DecisionEngine:
    return SemifDecisionEngine(model=requested_model)


_ENGINE_BUILDERS: dict[DecisionEngineName, EngineBuilder] = {
    DecisionEngineName.FIXTURE: _fixture_engine,
    DecisionEngineName.RULES: _rules_engine,
    DecisionEngineName.LLM: _llm_engine,
    DecisionEngineName.SEMIF: _semif_engine,
}

_DEFAULT_MODELS = {
    DecisionEngineName.FIXTURE: "recorded-fixture",
    DecisionEngineName.RULES: RULE_MODEL,
    DecisionEngineName.LLM: LLM_MODEL,
    DecisionEngineName.SEMIF: SEMIF_MODEL,
}

_MODEL_ENVIRONMENTS: dict[DecisionEngineName, str | None] = {
    DecisionEngineName.FIXTURE: None,
    DecisionEngineName.RULES: None,
    DecisionEngineName.LLM: "LLM_MODEL",
    DecisionEngineName.SEMIF: "SEMIF_MODEL",
}


def parse_decision_engine(value: str) -> DecisionEngineName:
    try:
        return DecisionEngineName(value.strip().casefold())
    except ValueError as error:
        allowed = ", ".join(engine.value for engine in DecisionEngineName)
        raise ValueError(f"DECISION_ENGINE must be one of: {allowed}") from error


def create_decision_engine(
    engine: DecisionEngineName | str,
    *,
    requested_model: str,
    fixture_path: Path,
) -> DecisionEngine:
    selected = engine if isinstance(engine, DecisionEngineName) else parse_decision_engine(engine)
    return _ENGINE_BUILDERS[selected](requested_model, fixture_path)
