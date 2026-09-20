# /// script
# requires-python = ">=3.13"
# dependencies = ["jsonschema==4.26.0"]
# ///
"""Validate dashboard response examples and their cross-response invariants."""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "contracts/api/examples"
EXPECTED_FILES = {
    "demo-metadata.json",
    "demo-overview.json",
    "demo-signal.json",
    "demo-trends.json",
    "demo-trends-candidate-statistical.json",
    "demo-evidence-page.json",
    "demo-evidence-detail.json",
    "live-uncalibrated-overview.json",
    "live-restricted-evidence-detail.json",
    "live-trends-awaiting-calibration.json",
    "demo-evaluation.json",
    "live-evaluation-awaiting-human-labels.json",
}


def main() -> None:
    schema = _read_json(ROOT / "contracts/api/dashboard-v1.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    paths = sorted(EXAMPLES.glob("*.json"))
    names = {path.name for path in paths}
    if names != EXPECTED_FILES:
        raise ValueError(
            "Dashboard example set differs from the documented journey: "
            f"missing={sorted(EXPECTED_FILES - names)}, extra={sorted(names - EXPECTED_FILES)}"
        )

    examples: dict[str, dict[str, Any]] = {}
    for path in paths:
        document = _read_json(path)
        errors = sorted(
            validator.iter_errors(document), key=lambda error: list(error.path)
        )
        if errors:
            locations = [
                (
                    f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: "
                    f"{error.message}"
                )
                for error in errors
            ]
            raise ValueError(
                f"{path.relative_to(ROOT)} is invalid:\n" + "\n".join(locations)
            )
        examples[path.name] = document

    _validate_demo_journey(examples)
    _validate_live_journey(examples)
    _validate_trend_journey(examples)
    _validate_evaluation_journey(examples)
    _validate_numeric_invariants(examples)
    print(
        f"Validated {len(paths)} dashboard example response(s) against dashboard-v1 "
        "and verified demo/live cross-response invariants."
    )


def _validate_demo_journey(examples: dict[str, dict[str, Any]]) -> None:
    metadata = examples["demo-metadata.json"]
    overview = examples["demo-overview.json"]
    signal = examples["demo-signal.json"]
    page = examples["demo-evidence-page.json"]
    detail = examples["demo-evidence-detail.json"]

    if any(
        document["context"] != "demo"
        for document in (metadata, overview, signal, page, detail)
    ):
        raise ValueError("Every demo journey response must declare the demo context")
    if (
        metadata["policyStatus"] != "illustrative"
        or not metadata["source"]["synthetic"]
    ):
        raise ValueError("Demo metadata must identify an illustrative synthetic source")
    if metadata["source"] not in metadata["sources"] or {
        source["datasetName"] for source in metadata["sources"]
    } != {
        "feedback-decision-semif",
        "feedback-decision-rules",
        "feedback-decision-ai-reference",
    }:
        raise ValueError(
            "Demo metadata must expose selectable SemIf, rules, and Sol sources"
        )

    filters = overview["filters"]
    if signal["filters"] != filters or page["filters"] != filters:
        raise ValueError(
            "Demo filters must flow unchanged through overview, signal, and evidence"
        )
    if (
        filters["sourceKey"] != metadata["source"]["key"]
        or detail["source"] != metadata["source"]
    ):
        raise ValueError("Demo source identity must remain stable across the journey")
    if (
        filters["from"] != metadata["availableRange"]["from"]
        or filters["toExclusive"] != metadata["availableRange"]["toExclusive"]
    ):
        raise ValueError("Demo filters must use the documented available range")

    overview_signal = overview["signals"][0]
    if signal["signal"] != overview_signal:
        raise ValueError(
            "Selected demo signal must be identical in overview and explorer responses"
        )
    if (
        page["signalId"] != overview_signal["id"]
        or filters["topic"] != overview_signal["id"]
    ):
        raise ValueError(
            "Selected signal id must remain stable through evidence pagination"
        )
    if signal["series"] != overview["series"]:
        raise ValueError(
            "Overview and signal examples must use the same derived series"
        )
    if page["total"] != overview_signal["numerator"]:
        raise ValueError("Demo evidence total must equal the selected signal numerator")
    if detail["record"] != page["items"][0]:
        raise ValueError("Demo detail must resolve the first stable evidence row")
    if detail["provenance"]["decisionId"] != detail["record"]["decisionId"]:
        raise ValueError(
            "Demo record and provenance must identify the same immutable decision"
        )
    if detail["evidence"]["access"] != "permitted_synthetic":
        raise ValueError(
            "Only explicitly permitted synthetic text may appear in the demo detail"
        )
    if detail["provenance"]["policyStatus"] != "illustrative":
        raise ValueError("Demo provenance must remain explicitly illustrative")
    if any(
        answer["eligibility"] != "illustrative_eligible" for answer in detail["answers"]
    ):
        raise ValueError("Demo answers must use illustrative eligibility only")

    ordered = sorted(
        page["items"],
        key=lambda row: (-_timestamp(row["occurredAt"]), row["feedbackId"]),
    )
    if page["items"] != ordered:
        raise ValueError(
            "Evidence rows must be ordered by occurredAt DESC, feedbackId ASC"
        )
    if len(page["items"]) > page["pageSize"] or page["total"] < len(page["items"]):
        raise ValueError("Evidence page counts are inconsistent")


def _validate_live_journey(examples: dict[str, dict[str, Any]]) -> None:
    overview = examples["live-uncalibrated-overview.json"]
    detail = examples["live-restricted-evidence-detail.json"]
    demo_metadata = examples["demo-metadata.json"]

    if overview["context"] != "live" or detail["context"] != "live":
        raise ValueError("Live examples must declare the live context")
    if overview["filters"]["sourceKey"] != detail["source"]["key"]:
        raise ValueError(
            "Live overview and detail must use one connected source identity"
        )
    if detail["source"]["key"] == demo_metadata["source"]["key"]:
        raise ValueError("Live and illustrative demo identities must remain separate")

    restricted = detail["record"]
    evidence = detail["evidence"]
    if (
        restricted["evidenceAccess"] != "restricted"
        or restricted["excerpt"] is not None
    ):
        raise ValueError("Restricted live rows must expose no excerpt")
    if evidence != {"access": "restricted", "title": None, "body": None}:
        raise ValueError("Restricted live detail title and body must be null")
    if detail["provenance"]["policyStatus"] != "awaiting_calibration":
        raise ValueError(
            "Live provenance must expose the current uncalibrated policy status"
        )
    if any(
        answer["eligibility"] != "withheld_uncalibrated" for answer in detail["answers"]
    ):
        raise ValueError(
            "Live answers must remain withheld while the policy is uncalibrated"
        )

    analytical_ids = {"analytical_coverage", "topic_rate"}
    metrics = {metric["id"]: metric for metric in overview["metrics"]}
    if not analytical_ids <= metrics.keys():
        raise ValueError(
            "Live overview must document coverage and topic-rate availability"
        )
    for metric_id in analytical_ids:
        metric = metrics[metric_id]
        if metric["value"] is not None or metric["availability"] != {
            "state": "unavailable",
            "reason": "uncalibrated",
        }:
            raise ValueError(
                f"{metric_id} must be null and unavailable while uncalibrated"
            )
    if any(
        point["eligibleCount"] != 0
        or point["topicNumerator"] != 0
        or point["value"] is not None
        for point in overview["series"]
    ):
        raise ValueError(
            "Live uncalibrated series must expose zero eligible facts and null values"
        )
    for signal in overview["signals"]:
        if (
            signal["denominator"] != 0
            or signal["rate"] is not None
            or signal["availability"]["state"] != "unavailable"
        ):
            raise ValueError(
                "Live signals with no eligible facts must remain unavailable"
            )


def _validate_numeric_invariants(examples: dict[str, dict[str, Any]]) -> None:
    for name, document in examples.items():
        for metric in document.get("metrics", []):
            _check_fraction(
                name, metric["numerator"], metric["denominator"], metric["value"]
            )
        if document.get("kind") in {"overview", "signal"}:
            for point in document.get("series", []):
                if (
                    not 0
                    <= point["topicNumerator"]
                    <= point["eligibleCount"]
                    <= point["importedCount"]
                ):
                    raise ValueError(f"{name} contains an impossible series count")
                _check_rate(
                    name,
                    point["topicNumerator"],
                    point["eligibleCount"],
                    point["value"],
                )
        signals = document.get("signals", [])
        if document.get("kind") == "signal":
            signals = [document["signal"]]
        for signal in signals:
            _check_fraction(
                name, signal["numerator"], signal["denominator"], signal["rate"]
            )
            comparison = signal["comparison"]
            if comparison is not None:
                _check_fraction(
                    name,
                    comparison["numerator"],
                    comparison["denominator"],
                    comparison["rate"],
                )
                expected_delta = signal["rate"] - comparison["rate"]
                if not math.isclose(
                    signal["deltaPoints"], expected_delta, abs_tol=0.05
                ):
                    raise ValueError(f"{name} has an inconsistent comparison delta")

    demo = examples["demo-overview.json"]
    if (
        sum(point["importedCount"] for point in demo["series"])
        != demo["processing"]["feedbackRecords"]
    ):
        raise ValueError(
            "Demo series imported counts must match processing feedback records"
        )
    selected = demo["signals"][0]
    if (
        sum(point["eligibleCount"] for point in demo["series"])
        != selected["denominator"]
    ):
        raise ValueError(
            "Demo series eligible counts must match the signal denominator"
        )
    if (
        sum(point["topicNumerator"] for point in demo["series"])
        != selected["numerator"]
    ):
        raise ValueError("Demo series topic counts must match the signal numerator")

    live = examples["live-uncalibrated-overview.json"]
    if (
        sum(point["importedCount"] for point in live["series"])
        != live["processing"]["feedbackRecords"]
    ):
        raise ValueError(
            "Live series imported counts must match processing feedback records"
        )


def _validate_trend_journey(examples: dict[str, dict[str, Any]]) -> None:
    demo = examples["demo-trends.json"]
    candidate = examples["demo-trends-candidate-statistical.json"]
    live = examples["live-trends-awaiting-calibration.json"]

    if demo["context"] != "demo" or demo["availability"] != {
        "state": "available",
        "reason": None,
    }:
        raise ValueError("Demo trends must be explicitly available in the demo context")
    if not demo["source"]["synthetic"]:
        raise ValueError("Demo trend evaluation must use a synthetic source")
    if live["context"] != "live" or live["availability"] != {
        "state": "unavailable",
        "reason": "awaiting_calibration",
    }:
        raise ValueError("Live trends must be unavailable while calibration is pending")
    if live["source"] is not None or live["summary"] is not None:
        raise ValueError(
            "Unavailable live trends must not invent a source or evaluation summary"
        )
    if any(live[key] for key in ("series", "results", "incidents")):
        raise ValueError(
            "Unavailable live trends must expose no series, results, or incidents"
        )
    if _contains_forbidden_live_field(live):
        raise ValueError(
            "Live trends must not expose scenario identifiers or raw feedback text"
        )

    method = demo["method"]
    if method != live["method"]:
        raise ValueError(
            "Demo and live trends must identify the same detector configuration"
        )
    if method["claim"] != "emerging_signal_not_statistical_significance":
        raise ValueError("The detector claim must not imply statistical significance")
    if candidate["method"]["id"] != "candidate_statistical":
        raise ValueError("The statistical trend example must identify its algorithm")
    if candidate["method"]["minimumProbabilityOfDirection"] != 0.98:
        raise ValueError("The statistical trend example must expose its posterior gate")
    if any(result["probabilityOfDirection"] is None for result in candidate["results"]):
        raise ValueError(
            "Statistical trend results must expose posterior probabilities"
        )

    series = {item["seriesId"]: item for item in demo["series"]}
    if len(series) != len(demo["series"]):
        raise ValueError("Trend series identifiers must be unique")
    results = {item["evaluationId"]: item for item in demo["results"]}
    if len(results) != len(demo["results"]):
        raise ValueError("Trend evaluation identifiers must be unique")

    for result in results.values():
        if result["seriesId"] not in series:
            raise ValueError("Every trend result must reference a declared series")
        current = result["current"]
        baseline = result["baseline"]
        _check_rate(
            "demo-trends.json",
            current["numerator"],
            current["denominator"],
            current["rate"],
        )
        _check_rate(
            "demo-trends.json",
            baseline["numerator"],
            baseline["denominator"],
            baseline["rate"],
        )
        _check_window_days(current["range"], method["currentWindowDays"])
        _check_window_days(baseline["range"], method["baselineWindowDays"])
        if baseline["range"]["toExclusive"] != current["range"]["from"]:
            raise ValueError("Baseline and current trend windows must be adjacent")
        if current["range"]["toExclusive"] != result["anchor"]:
            raise ValueError("A trend anchor must equal the current window end")
        expected_delta = current["rate"] - baseline["rate"]
        if not math.isclose(result["deltaPoints"], expected_delta, abs_tol=1e-6):
            raise ValueError("Trend deltaPoints must be a percentage-point difference")
        expected_ratio = (
            current["rate"] / baseline["rate"] if baseline["rate"] else None
        )
        expected_relative = (
            (expected_ratio - 1) * 100 if expected_ratio is not None else None
        )
        if not _nullable_close(result["rateRatio"], expected_ratio):
            raise ValueError(
                "Trend rateRatio must equal current rate divided by baseline rate"
            )
        if not _nullable_close(result["relativeChangePercent"], expected_relative):
            raise ValueError(
                "Trend relativeChangePercent is inconsistent with the rate ratio"
            )
        if result["state"] == "emerging_signal":
            _validate_emerging_gates(result, series[result["seriesId"]], method)

    incidents = demo["incidents"]
    expected_outcomes = {
        "product_defect_noise_increase",
        "delivery_delay_increase",
        "support_praise_increase",
        "return_unresolved_increase",
    }
    if {incident["outcome"] for incident in incidents} != expected_outcomes:
        raise ValueError("Demo trends must include all four planted incident outcomes")
    for incident in incidents:
        if not incident["incidentId"].startswith("synthetic-incident-"):
            raise ValueError("Demo incident identifiers must be clearly synthetic")
        if incident["seriesId"] not in series:
            raise ValueError("Every incident must reference a declared series")
        matched = incident["matchedEvaluationId"]
        if incident["detected"] and (
            matched not in results or results[matched]["state"] != "emerging_signal"
        ):
            raise ValueError("Detected incidents must reference an emerging evaluation")

    summary = demo["summary"]
    detected_count = sum(incident["detected"] for incident in incidents)
    alert_count = sum(
        result["state"] == "emerging_signal" for result in results.values()
    )
    matched_alerts = {
        incident["matchedEvaluationId"]
        for incident in incidents
        if incident["detected"]
    }
    false_alert_count = alert_count - len(matched_alerts)
    delays = [
        incident["detectionDelayDays"] for incident in incidents if incident["detected"]
    ]
    if (
        summary["plantedIncidentCount"] != len(incidents)
        or summary["alertEpisodeCount"] != alert_count
    ):
        raise ValueError(
            "Trend summary counts must match incidents and emerging evaluations"
        )
    if not math.isclose(
        summary["recall"], detected_count / len(incidents), abs_tol=1e-9
    ):
        raise ValueError("Trend recall is inconsistent with detected incidents")
    if not math.isclose(
        summary["precision"], len(matched_alerts) / alert_count, abs_tol=1e-9
    ):
        raise ValueError("Trend precision is inconsistent with matched alert episodes")
    if not math.isclose(
        summary["medianDetectionDelayDays"], statistics.median(delays), abs_tol=1e-9
    ):
        raise ValueError("Trend median detection delay is inconsistent with incidents")
    expected_false_rate = false_alert_count / summary["evaluableSeriesDayCount"] * 100
    if not math.isclose(
        summary["falseAlertEpisodesPer100SeriesDays"], expected_false_rate, abs_tol=1e-9
    ):
        raise ValueError(
            "Trend false-alert episode rate is inconsistent with the evaluation counts"
        )


def _validate_evaluation_journey(examples: dict[str, dict[str, Any]]) -> None:
    demo = examples["demo-evaluation.json"]
    live = examples["live-evaluation-awaiting-human-labels.json"]
    if demo["context"] != "demo" or demo["availability"] != {
        "state": "available",
        "reason": None,
    }:
        raise ValueError("Demo evaluation must be explicitly available")
    if demo["status"] != "complete" or demo["reference"] != {
        "kind": "ai_reviewed_not_human_gold",
        "model": "gpt-5.6-sol",
        "reasoning": "medium",
    }:
        raise ValueError(
            "Demo evaluation must identify the interim Sol-medium AI reference"
        )
    if demo["recordCount"] != 480 or demo["successCount"] + demo["errorCount"] != 480:
        raise ValueError("Demo evaluation counts must cover all 480 records")
    if sum(item["recordCount"] for item in demo["semifLanguageSlices"]) != 480:
        raise ValueError("SemIf evaluation language slices must cover all records")
    if sum(item["recordCount"] for item in demo["ruleLanguageSlices"]) != 480:
        raise ValueError("Rule evaluation language slices must cover all records")
    if sum(item["recordCount"] for item in demo["llmLanguageSlices"]) != 192:
        raise ValueError("LLM language slices must cover the 192 completed records")
    for item in demo["semifLanguageSlices"]:
        if item["successCount"] + item["errorCount"] != item["recordCount"]:
            raise ValueError("Evaluation language-slice counts are inconsistent")
    if live["context"] != "live" or live["availability"] != {
        "state": "unavailable",
        "reason": "awaiting_human_labels",
    }:
        raise ValueError("Live evaluation must remain unavailable pending human labels")
    if any(
        live[key] is not None
        for key in (
            "reference",
            "semif",
            "semifPrimaryTopic",
            "rules",
            "rulePrimaryTopic",
            "llm",
            "semifCost",
            "llmCost",
            "llmPrimaryTopic",
        )
    ):
        raise ValueError("Live evaluation must not expose interim demo results")


def _validate_emerging_gates(
    result: dict[str, Any], series: dict[str, Any], method: dict[str, Any]
) -> None:
    current = result["current"]
    baseline = result["baseline"]
    relative = result["relativeChangePercent"]
    gates_hold = (
        current["denominator"] >= method["minimumCurrentDenominator"]
        and baseline["denominator"] >= method["minimumBaselineDenominator"]
        and current["numerator"] >= method["minimumCurrentNumerator"]
        and abs(result["deltaPoints"]) >= method["minimumAbsoluteDeltaPoints"]
        and relative is not None
        and abs(relative) >= method["minimumRelativeChangePercent"]
        and (
            result["deltaPoints"] > 0
            if series["direction"] == "increase"
            else result["deltaPoints"] < 0
        )
    )
    failed_reasons = [
        reason for reason in result["gateReasons"] if "below_minimum" in reason
    ]
    if not gates_hold or failed_reasons:
        raise ValueError(
            f"Emerging evaluation {result['evaluationId']} has a failed detector gate"
        )


def _check_window_days(window: dict[str, str], expected_days: int) -> None:
    from_value = datetime.fromisoformat(window["from"].replace("Z", "+00:00"))
    to_value = datetime.fromisoformat(window["toExclusive"].replace("Z", "+00:00"))
    if (to_value - from_value).total_seconds() != expected_days * 86400:
        raise ValueError(f"Trend window must contain exactly {expected_days} UTC days")


def _nullable_close(actual: float | None, expected: float | None) -> bool:
    return (actual is None and expected is None) or (
        actual is not None
        and expected is not None
        and math.isclose(actual, expected, abs_tol=1e-6)
    )


def _contains_forbidden_live_field(value: Any) -> bool:
    forbidden = {"scenarioId", "scenarioIds", "body", "excerpt", "rawText"}
    if isinstance(value, dict):
        return any(
            key in forbidden or _contains_forbidden_live_field(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_live_field(item) for item in value)
    return False


def _check_fraction(
    name: str, numerator: int | None, denominator: int | None, value: float | None
) -> None:
    if numerator is not None and denominator is not None and numerator > denominator:
        raise ValueError(f"{name} has a numerator greater than its denominator")
    if numerator is not None and denominator is not None:
        _check_rate(name, numerator, denominator, value)


def _check_rate(
    name: str, numerator: int, denominator: int, value: float | None
) -> None:
    if denominator == 0:
        if value is not None:
            raise ValueError(f"{name} must use null for a zero-denominator rate")
        return
    if value is None:
        return
    expected = numerator / denominator * 100
    if not math.isclose(value, expected, abs_tol=0.05):
        raise ValueError(
            f"{name} rate {value} does not match {numerator}/{denominator}"
        )


def _read_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return document


def _timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


if __name__ == "__main__":
    main()
