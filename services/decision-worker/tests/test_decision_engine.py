"""Frozen-schema, live-adapter mapping, and fixture replay tests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from _pytest.capture import CaptureFixture
from system_one_adapter import (
    SystemOneAdapterClient,
)
from system_one_adapter import (
    SystemOneResponse as AdapterSystemOneResponse,
)
from system_one_adapter import (
    Usage as AdapterUsage,
)
from typesafe_sdk import (
    Choice,
    ChoiceAnswer,
    Noul,
    NoulAnswer,
    Score,
    ScoreAnswer,
    SystemOneResponse,
    Usage,
)

from feedback_intelligence_worker.data.models import (
    FeedbackRecord,
    SourceReference,
    canonical_feedback_id,
)
from feedback_intelligence_worker.decision.cli import main as decision_main
from feedback_intelligence_worker.decision.envelope import build_decision_envelope
from feedback_intelligence_worker.decision.fixture import FixtureDecisionEngine
from feedback_intelligence_worker.decision.llm import LLM_MODEL, LlmSystemOneDecisionEngine
from feedback_intelligence_worker.decision.models import (
    ChoiceDecision,
    NoulDecision,
    ScoreDecision,
)
from feedback_intelligence_worker.decision.recording import write_fixture_set
from feedback_intelligence_worker.decision.rules import RULE_MODEL, RuleDecisionEngine
from feedback_intelligence_worker.decision.schema import (
    DecisionSchema,
    Primitive,
    load_decision_schema,
)
from feedback_intelligence_worker.decision.semif import (
    SEMIF_MODEL,
    SemifDecisionEngine,
)
from feedback_intelligence_worker.decision.system_one import question_payloads
from feedback_intelligence_worker.privacy import PrivacyBoundary
from feedback_intelligence_worker.privacy.models import ModelSafeFeedbackState, RedactionSummary


@pytest.fixture(scope="module")
def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def schema(repository_root: Path) -> DecisionSchema:
    return load_decision_schema(repository_root / "schemas/feedback-decision/1.0.0/manifest.json")


@pytest.fixture
def safe_state() -> ModelSafeFeedbackState:
    record = FeedbackRecord(
        feedback_id=canonical_feedback_id("test", "decision-engine"),
        source=SourceReference("test", "Decision test", "1.0.0", "decision-engine"),
        original_text="The product keeps restarting, but delivery was quick.",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        language="en-GB",
        channel="product_review",
    )
    return PrivacyBoundary().prepare_for_decision(record)


def test_manifest_freezes_fourteen_typed_questions(schema: DecisionSchema) -> None:
    assert schema.identity == "feedback-decision/1.0.0"
    assert schema.allowed_state_fields == ("feedback_text", "language", "channel")
    assert len(schema.questions) == 14
    assert {
        primitive: sum(q.primitive is primitive for q in schema.questions)
        for primitive in Primitive
    } == {
        Primitive.CHOICE: 3,
        Primitive.SCORE: 5,
        Primitive.NOUL: 6,
    }
    assert schema.question("primary_topic").options[-1].option_id == "other"
    assert tuple(level.value for level in schema.question("issue_severity").levels) == (
        0,
        1,
        2,
        3,
    )
    assert "scenario_id" in schema.prohibited_state_fields
    assert schema.sha256.startswith("sha256:")


def test_manifest_translates_to_official_sdk_primitives(schema: DecisionSchema) -> None:
    payloads = question_payloads(schema)

    assert len(payloads) == 14
    assert isinstance(payloads["primary_topic"], Choice)
    assert isinstance(payloads["overall_experience"], Score)
    assert isinstance(payloads["reports_product_defect"], Noul)


def test_llm_adapter_reuses_questions_and_records_cumulative_retry_usage(
    schema: DecisionSchema,
    safe_state: ModelSafeFeedbackState,
) -> None:
    response = _adapter_response_for(schema)
    client = CapturingAdapterClient(response)
    engine = LlmSystemOneDecisionEngine(
        client=cast(SystemOneAdapterClient, client),
    )

    result = engine.decide(safe_state, schema)

    assert client.calls == 1
    assert client.provider == "openai"
    assert client.model == LLM_MODEL
    assert client.state == {
        "feedback_text": "The product keeps restarting, but delivery was quick.",
        "language": "en-GB",
        "channel": "product_review",
    }
    assert client.questions is not None
    assert set(client.questions) == {question.question_id for question in schema.questions}
    assert result.provider == "llm-openai"
    assert result.requested_model == LLM_MODEL
    assert result.resolved_model == LLM_MODEL
    assert result.input_tokens == 444
    assert result.output_tokens == 66


def test_llm_adapter_requires_dated_snapshot_and_live_credential(
    schema: DecisionSchema,
    safe_state: ModelSafeFeedbackState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="dated model snapshot"):
        LlmSystemOneDecisionEngine(model="gpt-5.4-mini")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        LlmSystemOneDecisionEngine().decide(safe_state, schema)


def test_semif_adapter_maps_runtime_options_without_exposing_extra_state(
    schema: DecisionSchema,
    safe_state: ModelSafeFeedbackState,
) -> None:
    scorer = CapturingSemifScorer()
    engine = SemifDecisionEngine(scorer=scorer)

    result = engine.decide(safe_state, schema)

    assert len(scorer.rows) == 14
    assert {row["id"] for row in scorer.rows} == {
        question.question_id for question in schema.questions
    }
    assert {tuple(row["state"]) for row in scorer.rows} == {
        ("feedback_text", "language", "channel")
    }
    assert result.provider == "semif"
    assert result.requested_model == SEMIF_MODEL
    assert result.resolved_model == SEMIF_MODEL
    assert result.output_tokens == 0
    assert result.input_tokens == 1400
    assert cast(ChoiceDecision, result.answers["primary_topic"]).choice == "product_quality"
    assert cast(NoulDecision, result.answers["mentions_product"]).noul == pytest.approx(0.7)
    assert cast(ScoreDecision, result.answers["overall_experience"]).score == pytest.approx(0.75)


def test_semif_adapter_requires_the_frozen_model_identity() -> None:
    with pytest.raises(ValueError, match="supports only"):
        SemifDecisionEngine(model="Qwen/Qwen3.5-4B")


def test_recorded_fixture_replays_without_text_or_credentials(
    schema: DecisionSchema,
    safe_state: ModelSafeFeedbackState,
    tmp_path: Path,
) -> None:
    live_result = RuleDecisionEngine().decide(safe_state, schema)
    fixture_path = tmp_path / "decisions.json"
    write_fixture_set(
        fixture_path,
        schema=schema,
        recordings=[(safe_state, live_result)],
    )

    fixture_text = fixture_path.read_text(encoding="utf-8")
    assert safe_state.redacted_text not in fixture_text
    assert "feedback_text" not in fixture_text
    replayed = FixtureDecisionEngine(fixture_path).decide(safe_state, schema)
    assert replayed.provider == "fixture"
    assert replayed.recorded_provider == "rules"
    assert replayed.answers == live_result.answers


def test_envelope_retains_provenance_but_no_feedback_body(
    schema: DecisionSchema,
    safe_state: ModelSafeFeedbackState,
) -> None:
    result = RuleDecisionEngine().decide(safe_state, schema)
    envelope = build_decision_envelope(
        safe_state,
        schema,
        result,
        decided_at=datetime(2026, 9, 19, tzinfo=UTC),
    )
    serialized = json.dumps(envelope)

    assert safe_state.redacted_text not in serialized
    assert envelope["policy"] is None
    assert envelope["schema"] == {
        "name": "feedback-decision",
        "version": "1.0.0",
        "sha256": schema.sha256,
    }
    assert envelope["input"] == {
        "redacted_text_sha256": safe_state.redacted_text_sha256,
        "language": "en-GB",
        "channel": "product_review",
    }


def test_default_fixture_mode_processes_committed_demo_without_key(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DECISION_ENGINE", raising=False)
    output = tmp_path / "decisions.jsonl"

    assert decision_main(["synthetic", "--output", str(output), "--json"]) == 0

    summary = json.loads(capsys.readouterr().out)
    assert summary["engine"] == "fixture"
    assert summary["decisions_written"] == 9
    decisions = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(decisions) == 9
    assert {decision["engine"]["provider"] for decision in decisions} == {"fixture"}
    assert {decision["engine"]["recorded_provider"] for decision in decisions} == {"semif"}


@pytest.mark.parametrize(
    ("text", "channel", "topic", "severity", "defect_type"),
    [
        (
            "Tracking did not update and the parcel arrived 7 days late.",
            "delivery_survey",
            "delivery",
            2.0,
            "unclear",
        ),
        (
            "Produkten slutade fungera efter en vecka och kopplar nu ner slumpmässigt.",
            "product_review",
            "product_quality",
            3.0,
            "stability",
        ),
        (
            "Support explained the checks clearly and solved the issue on the first contact.",
            "support_ticket",
            "support",
            0.0,
            "unclear",
        ),
        (
            "The return was received 12 days ago, but the refund is still missing.",
            "return_feedback",
            "returns_refunds",
            2.0,
            "unclear",
        ),
    ],
)
def test_rule_baseline_maps_bilingual_lexicons_with_fixed_precedence(
    schema: DecisionSchema,
    text: str,
    channel: str,
    topic: str,
    severity: float,
    defect_type: str,
) -> None:
    state = ModelSafeFeedbackState(
        feedback_id="00000000-0000-4000-8000-000000000001",
        redacted_text=text,
        redacted_text_sha256="sha256:" + "0" * 64,
        source_provider_id="test",
        language="sv-SE" if "Produkten" in text else "en-GB",
        channel=channel,
        redactions=RedactionSummary(),
    )

    result = RuleDecisionEngine().decide(state, schema)

    assert result.provider == "rules"
    assert result.requested_model == RULE_MODEL
    assert cast(ChoiceDecision, result.answers["primary_topic"]).choice == topic
    assert cast(ScoreDecision, result.answers["issue_severity"]).score == severity
    assert cast(ChoiceDecision, result.answers["defect_type"]).choice == defect_type


class CapturingSemifScorer:
    def __init__(self) -> None:
        self.rows: list[Mapping[str, Any]] = []

    def score(
        self,
        rows: Sequence[Mapping[str, Any]],
    ) -> Sequence[Mapping[str, Any]]:
        self.rows = list(rows)
        results: list[Mapping[str, Any]] = []
        for row in rows:
            options = cast(list[dict[str, str]], row["options"])
            tail = 0.3 / (len(options) - 1)
            results.append(
                {
                    "id": row["id"],
                    "option_ids": [option["id"] for option in options],
                    "probabilities": [0.7 if index == 0 else tail for index in range(len(options))],
                    "input_tokens": 100,
                }
            )
        return results


class CapturingAdapterClient:
    def __init__(self, response: AdapterSystemOneResponse) -> None:
        self.response = response
        self.calls = 0
        self.state: object = None
        self.questions: Mapping[str, object] | None = None
        self.provider: str | None = None
        self.model: str | None = None

    def system_one(
        self,
        state: object,
        questions: Mapping[str, object],
        *,
        provider: str,
        model: str,
    ) -> AdapterSystemOneResponse:
        self.calls += 1
        self.state = state
        self.questions = questions
        self.provider = provider
        self.model = model
        return self.response


def _response_for(schema: DecisionSchema) -> SystemOneResponse:
    answers: dict[str, ChoiceAnswer | ScoreAnswer | NoulAnswer] = {}
    for question in schema.questions:
        if question.primitive is Primitive.CHOICE:
            option_ids = [option.option_id for option in question.options]
            remainder = 0.2 / (len(option_ids) - 1)
            answers[question.question_id] = ChoiceAnswer(
                choice=option_ids[0],
                confidence=0.75,
                probabilities={
                    option_id: 0.8 if index == 0 else remainder
                    for index, option_id in enumerate(option_ids)
                },
            )
        elif question.primitive is Primitive.SCORE:
            probability = 1 / len(question.levels)
            answers[question.question_id] = ScoreAnswer(
                score=float((len(question.levels) - 1) / 2),
                confidence=0.7,
                legend={level.value: level.description for level in question.levels},
                probabilities={level.value: probability for level in question.levels},
            )
        else:
            answers[question.question_id] = NoulAnswer(noul=0.7)
    return SystemOneResponse(
        model=LLM_MODEL,
        usage=Usage(input_tokens=321, output_tokens=45),
        answers=answers,
    )


def _adapter_response_for(schema: DecisionSchema) -> AdapterSystemOneResponse:
    base = _response_for(schema)
    return AdapterSystemOneResponse(
        model=LLM_MODEL,
        usage=AdapterUsage(
            input_tokens=123,
            output_tokens=21,
            input_tokens_total=444,
            output_tokens_total=66,
            n_retries=1,
            n_retries_malformed_structure=1,
            latency=1.25,
        ),
        answers=base.answers,
        debug={},
    )
