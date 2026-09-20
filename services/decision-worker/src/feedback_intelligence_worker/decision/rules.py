"""Deterministic bilingual rule baseline for the feedback decision schema."""

from __future__ import annotations

from dataclasses import dataclass

from feedback_intelligence_worker.decision.models import (
    ChoiceDecision,
    DecisionAnswer,
    DecisionEngineResult,
    NoulDecision,
    ScoreDecision,
    validate_engine_result,
)
from feedback_intelligence_worker.decision.schema import DecisionSchema, Primitive, QuestionSpec
from feedback_intelligence_worker.privacy.models import ModelSafeFeedbackState

RULE_MODEL = "rules-1.0.0"


@dataclass(frozen=True, slots=True)
class _Outcome:
    primary_topic: str
    mentions_product: bool
    mentions_delivery: bool
    mentions_support: bool
    overall_experience: int
    product_experience: int
    delivery_experience: int
    support_experience: int
    reports_product_defect: bool
    issue_severity: int
    resolution_status: str
    actionable_feedback: bool
    explicit_repurchase_risk: bool
    defect_type: str


class RuleDecisionEngine:
    """Inspect a small, explicit English/Swedish lexicon with fixed precedence.

    This baseline intentionally has no learned parameters and reads only the same
    model-safe text, language, and channel fields exposed to external engines.
    """

    provider_id = "rules"

    def __init__(self, model: str = RULE_MODEL) -> None:
        if model != RULE_MODEL:
            raise ValueError(f"RuleDecisionEngine supports only {RULE_MODEL}")
        self._model = model

    def decide(
        self,
        state: ModelSafeFeedbackState,
        schema: DecisionSchema,
    ) -> DecisionEngineResult:
        outcome = _classify(state.redacted_text.casefold(), (state.channel or "").casefold())
        values: dict[str, str | int | bool] = {
            field: getattr(outcome, field) for field in outcome.__dataclass_fields__
        }
        answers: dict[str, DecisionAnswer] = {}
        for question in schema.questions:
            value = values[question.question_id]
            if question.primitive is Primitive.CHOICE:
                answers[question.question_id] = _choice(question, str(value))
            elif question.primitive is Primitive.SCORE:
                answers[question.question_id] = _score(question, int(value))
            else:
                answers[question.question_id] = NoulDecision(noul=0.9 if bool(value) else 0.1)
        result = DecisionEngineResult(
            provider=self.provider_id,
            requested_model=self._model,
            resolved_model=self._model,
            answers=answers,
            latency_ms=0,
        )
        validate_engine_result(result, schema)
        return result


def _classify(text: str, channel: str) -> _Outcome:
    irrelevant = _has(
        text,
        "browsing during lunch",
        "coffee near the shop",
        "no product feedback",
        "tittade runt på lunchen",
        "kaffet nära butiken",
        "ingen produktfeedback",
    )
    support = _has(text, "support", "agent", "kundtjänst", "supporten")
    returns = (
        _has(
            text,
            "return",
            "refund",
            "replacement",
            "sent the item back",
            "retur",
            "återbetal",
            "ersättningsvara",
            "ersättningsprodukt",
            "skickade tillbaka",
        )
        and not support
    )
    checkout = _has(text, "checkout", "basket", "payment", "kassan", "varukorg", "betalning")
    product_information = _has(
        text,
        "specifications",
        "dimensions",
        "setup guide",
        "compatibility section",
        "installationsguiden",
        "måtten",
        "specifikationerna",
    )
    price = _has(text, "price", "value", "expensive", "prisvärd", "värde för pengarna", "dyrare")
    compatibility = _has(
        text,
        "not compatible",
        "connector does not fit",
        "inte kompatibel",
        "kontakten inte passar",
    )
    noise = _has(text, "buzz", "whining", "noise", "surrande", "vinande ljud")
    stability = _has(
        text,
        "disconnect",
        "restart",
        "stopped working",
        "wont start",
        "kopplar nu ner",
        "omstart",
        "slutade fungera",
        "funkar inte alls",
    )
    physical_damage = _has(
        text,
        "damaged",
        "damged",
        "part was loose",
        "skadad",
        "satt löst",
        "trasig",
    )
    defect = noise or stability or physical_damage
    delivery = (
        _has(
            text,
            "delivery",
            "tracking",
            "parcel",
            "package",
            "leverans",
            "spårning",
            "paket",
            "vid leverans",
        )
        and not returns
    )

    if irrelevant:
        topic = "other"
    elif support:
        topic = "support"
    elif returns:
        topic = "returns_refunds"
    elif checkout:
        topic = "website_checkout"
    elif product_information:
        topic = "product_information"
    elif price:
        topic = "price_value"
    elif compatibility:
        topic = "compatibility"
    elif defect:
        topic = "product_quality"
    elif delivery:
        topic = "delivery"
    else:
        topic = "product_quality" if channel == "product_review" else "other"

    mentions_product = (
        channel == "product_review"
        or topic in {"product_quality", "compatibility", "price_value", "product_information"}
        or _has(text, "product", "produkten", "produktfiltren", "working product")
    ) and not irrelevant
    mentions_support = support
    mentions_delivery = delivery

    resolved = _has(
        text,
        "solved",
        "completed without trouble",
        "replacement immediately",
        "replacement was sent",
        "second attempt worked",
        "löst problemet",
        "gick igenom utan problem",
        "ersättningsprodukt direkt",
        "ersättningsvara skickades",
        "andra försöket fungerade",
    )
    unresolved = _has(
        text,
        "still missing",
        "cannot get a clear update",
        "remains unresolved",
        "do not have an answer",
        "failed because",
        "not compatible",
        "stopped working",
        "wont start",
        "buzz",
        "whining",
        "restart",
        "saknas fortfarande",
        "inget tydligt besked",
        "fortfarande olöst",
        "saknar fortfarande en lösning",
        "misslyckades eftersom",
        "inte kompatibel",
        "slutade fungera",
        "funkar inte",
        "surrande",
        "vinande ljud",
        "omstart",
        "skadad",
        "trasig",
        "damaged",
        "damged",
    )

    if resolved:
        resolution = "resolved"
    elif unresolved or defect or compatibility:
        resolution = "unresolved"
    elif topic in {"other", "product_quality", "price_value", "delivery"} and not _issue(text):
        resolution = "not_applicable"
    else:
        resolution = "unclear"

    product_score = 2
    delivery_score = 2
    support_score = 2
    overall = 2
    severity = 0

    if stability or _has(text, "wont start", "funkar inte alls"):
        overall = product_score = 0
        severity = 3 if not _has(text, "restart", "omstart") else 2
    elif physical_damage:
        total_failure = _has(text, "wont start", "funkar inte alls")
        overall = product_score = 0 if total_failure else 1
        delivery_score = 1
        severity = 3 if total_failure else 2
    elif noise:
        mild_noise = _has(text, "performs well", "presterar bra")
        overall = product_score = 2 if mild_noise else 1
        severity = 1 if mild_noise else 2
    elif compatibility:
        overall = product_score = 1
        severity = 3
    elif support:
        if resolved:
            overall = support_score = 4
            severity = 2 if _has(text, "replacement", "ersättningsprodukt") else 0
        else:
            overall = 0 if _has(text, "working product") else 1
            product_score = 0 if _has(text, "working product") else 2
            support_score = overall
            severity = 3 if _has(text, "working product") else 2
    elif returns:
        if resolved:
            overall = 3 if _has(text, "replacement was sent", "ersättningsvara skickades") else 4
            severity = 0
        else:
            overall = 1
            severity = 2
    elif delivery:
        positive_delivery = _has(
            text,
            "quicker than expected",
            "early delivery",
            "snabbare än väntat",
            "tidig leverans",
        )
        if positive_delivery:
            overall = delivery_score = 4
        else:
            overall = delivery_score = 1
            product_score = 3 if _has(text, "product is fine", "produkten är bra") else 2
            severity = 1 if _has(text, "frustrating") else 2
    elif price:
        overall = product_score = 3
        severity = 1 if _has(text, "accessories", "tillbehören") else 0
    elif product_information:
        positive_product = _has(text, "fast and quiet", "snabb och tyst", "bra prestanda")
        overall = product_score = 3 if positive_product else 2
        severity = 1
    elif checkout:
        overall = 2
        severity = 1
    elif _has(text, "really pleased", "mycket nöjd", "excellent so far", "riktigt bra"):
        overall = product_score = 4
    elif _has(text, "works exactly as expected", "fungerar precis som förväntat"):
        overall = product_score = 3
    elif _has(text, "frustrating", "frustrerande"):
        overall = 1
        product_score = 3
        delivery_score = 1
        severity = 1
    elif _has(text, "great speed", "installationen tog hela kvällen"):
        overall = product_score = 2
        severity = 1

    if noise:
        defect_type = "noise"
    elif stability:
        defect_type = "stability"
    elif physical_damage:
        defect_type = "physical_damage" if not _has(text, "kom trasig") else "other"
    else:
        defect_type = "unclear"

    vague = _has(text, "nothing stands out", "inget sticker ut")
    repurchase_risk = _has(
        text,
        "will not buy again",
        "won't buy again",
        "wont buy again",
        "never buying again",
        "kommer inte köpa igen",
        "aldrig handla igen",
    )
    return _Outcome(
        primary_topic=topic,
        mentions_product=mentions_product,
        mentions_delivery=mentions_delivery,
        mentions_support=mentions_support,
        overall_experience=overall,
        product_experience=product_score,
        delivery_experience=delivery_score,
        support_experience=support_score,
        reports_product_defect=defect,
        issue_severity=severity,
        resolution_status=resolution,
        actionable_feedback=not irrelevant and not vague,
        explicit_repurchase_risk=repurchase_risk,
        defect_type=defect_type,
    )


def _issue(text: str) -> bool:
    return _has(
        text,
        "but",
        "although",
        "yet",
        "failed",
        "late",
        "missing",
        "problem",
        "men",
        "inte",
        "saknas",
        "sent",
        "svåra",
        "otydlig",
        "för många steg",
    )


def _has(text: str, *phrases: str) -> bool:
    return any(phrase in text for phrase in phrases)


def _choice(question: QuestionSpec, selected: str) -> ChoiceDecision:
    option_ids = [option.option_id for option in question.options]
    confidence = 0.82 if selected not in {"other", "unclear"} else 0.68
    remainder = (1.0 - confidence) / (len(option_ids) - 1)
    probabilities = {
        option_id: confidence if option_id == selected else remainder for option_id in option_ids
    }
    return ChoiceDecision(selected, probabilities, confidence)


def _score(question: QuestionSpec, selected: int) -> ScoreDecision:
    level_ids = [level.value for level in question.levels]
    confidence = 0.8
    remainder = (1.0 - confidence) / (len(level_ids) - 1)
    probabilities = {
        level_id: confidence if level_id == selected else remainder for level_id in level_ids
    }
    return ScoreDecision(
        score=float(selected),
        probabilities=probabilities,
        confidence=confidence,
        legend={level.value: level.label for level in question.levels},
    )
