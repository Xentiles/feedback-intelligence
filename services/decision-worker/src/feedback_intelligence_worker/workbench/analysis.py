"""Explainable rules and descriptive results, separate from calibrated analytics."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

from feedback_intelligence_worker.privacy import PrivacyBoundary
from feedback_intelligence_worker.trends.detector import detect_rate_change
from feedback_intelligence_worker.trends.models import DailyObservation, DetectorConfig
from feedback_intelligence_worker.trends.statistical import detect_beta_binomial_change
from feedback_intelligence_worker.workbench.imports import normalize

PROTOCOL = {
    "version": "workbench-analysis/1.0.0",
    "currentDays": 7,
    "baselineDays": 28,
    "minCurrent": 10,
    "minBaseline": 20,
    "minPositive": 3,
    "minDelta": 5,
    "minRelative": 20,
    "minProbability": 0.95,
    "coverage": "observed_dates_only",
}
PROTOCOL_HASH = hashlib.sha256(json.dumps(PROTOCOL, sort_keys=True).encode()).hexdigest()


@lru_cache(maxsize=4096)
def phrase_pattern(phrase: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)")


def builtin_templates() -> list[dict[str, Any]]:
    retail = [
        ("support", "Customer service and assistance", ["support", "agent", "kundtjänst"]),
        ("returns_refunds", "Returns and refunds", ["refund", "return", "retur", "återbetal"]),
        ("website_checkout", "Website and checkout", ["checkout", "website", "kassa", "webbplats"]),
        (
            "compatibility",
            "Compatibility and fit",
            ["compatible", "compatibility", "passar", "kompatibel"],
        ),
        (
            "product_quality",
            "Product performance and defects",
            ["product", "broken", "defect", "produkt", "trasig"],
        ),
        (
            "delivery",
            "Shipping and fulfilment",
            ["delivery", "parcel", "shipping", "leverans", "paket"],
        ),
        ("price_value", "Price and value", ["price", "value", "expensive", "pris", "dyr"]),
    ]
    general = [
        (
            "service",
            "Service and assistance",
            ["service", "support", "staff", "kundtjänst", "personal"],
        ),
        (
            "quality",
            "Quality and reliability",
            ["quality", "broken", "reliable", "kvalitet", "trasig"],
        ),
        (
            "usability",
            "Ease of use and accessibility",
            ["easy", "difficult", "usable", "enkel", "svår"],
        ),
        ("value", "Price and value", ["price", "expensive", "value", "pris", "dyr"]),
        ("delivery", "Delivery and availability", ["delivery", "shipping", "leverans"]),
    ]
    return [
        {
            "name": name,
            "topics": [
                {
                    "id": key,
                    "label": key.replace("_", " ").title(),
                    "description": description,
                    "keywords": keywords,
                    "priority": i,
                }
                for i, (key, description, keywords) in enumerate(topics)
            ],
        }
        for name, topics in [("General feedback", general), ("Retail feedback", retail)]
    ]


def validate_template(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value.get("name"), str) or not 1 <= len(value["name"]) <= 100:
        raise ValueError("Template name must be 1-100 characters")
    topics = value.get("topics")
    if not isinstance(topics, list) or not 1 <= len(topics) <= 30:
        raise ValueError("Define 1-30 topics")
    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for topic in topics:
        if not isinstance(topic, dict) or not re.fullmatch(
            r"[a-z][a-z0-9_]{0,49}", str(topic.get("id", ""))
        ):
            raise ValueError("Topic ID must use lowercase letters, digits and underscores")
        if topic["id"] in seen or topic["id"] == "unclassified":
            raise ValueError("Topic IDs must be unique; unclassified is reserved")
        seen.add(topic["id"])
        for field, limit in [("label", 100), ("description", 1000)]:
            if not isinstance(topic.get(field), str) or not 1 <= len(topic[field]) <= limit:
                raise ValueError(f"Topic {field} is required and exceeds its limit")
        keywords = topic.get("keywords", [])
        if (
            not isinstance(keywords, list)
            or len(keywords) > 100
            or any(not isinstance(k, str) or not 1 <= len(k.strip()) <= 100 for k in keywords)
        ):
            raise ValueError("Use at most 100 non-empty keywords of at most 100 characters")
        priority = topic.get("priority", 0)
        if not isinstance(priority, int) or isinstance(priority, bool) or not 0 <= priority <= 1000:
            raise ValueError("Priority must be an integer from 0 to 1000")
        cleaned.append({**topic, "keywords": list(dict.fromkeys(normalize(k) for k in keywords))})
    payload = {"name": value["name"], "topics": cleaned}
    return {
        **payload,
        "revision": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
    }


def prepare(record: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, int]]:
    state = PrivacyBoundary().prepare_text(
        feedback_id=record["id"],
        text=record["text"],
        source_provider_id="workbench",
        language=record.get("language"),
        channel=record.get("channel"),
    )
    return state.redacted_text, state.to_decision_state(), state.redactions.to_dict()


def rule_classify(record: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    text, state, redactions = prepare(record)
    normalized = normalize(text)
    matches = []
    for topic in template["topics"]:
        phrases = [word for word in topic["keywords"] if phrase_pattern(word).search(normalized)]
        if phrases:
            matches.append(
                {"topic": topic["id"], "phrases": phrases, "priority": topic["priority"]}
            )
    matches.sort(key=lambda match: (match["priority"], match["topic"]))
    language = (record.get("language") or "").split("-")[0]
    sentiment = None
    positive: list[str] = []
    negative: list[str] = []
    if language in ("en", "sv"):
        positive = [
            word
            for word in [
                "good",
                "great",
                "excellent",
                "love",
                "easy",
                "bra",
                "fantastisk",
                "nöjd",
                "enkel",
            ]
            if re.search(r"(?<!\w)" + word + r"(?!\w)", normalized)
        ]
        negative = [
            word
            for word in [
                "bad",
                "broken",
                "poor",
                "late",
                "difficult",
                "dålig",
                "trasig",
                "sen",
                "svår",
            ]
            if re.search(r"(?<!\w)" + word + r"(?!\w)", normalized)
        ]
        sentiment = (
            "mixed"
            if positive and negative
            else "positive"
            if positive
            else "negative"
            if negative
            else "neutral"
        )
    actionable = bool(
        negative
        or any(word in normalized for word in ("please", "should", "suggest", "borde", "önskar"))
    )
    return {
        "schemaVersion": "workbench-classification/1.0.0",
        "topic": matches[0]["topic"] if matches else "unclassified",
        "sentiment": sentiment,
        "actionable": actionable,
        "redactedText": text,
        "redactions": redactions,
        "inputStateSha256": hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest(),
        "matches": matches,
        "sentimentMatches": {"positive": positive, "negative": negative},
        "requestedModel": "keywords-1.0.0",
        "resolvedModel": "keywords-1.0.0",
        "inputTokens": 0,
        "outputTokens": 0,
        "latencyMs": 0,
        "calibrated": False,
    }


def sample_records(records: list[dict[str, Any]], count: int = 25) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(records, key=lambda r: hashlib.sha256(r["id"].encode()).hexdigest()):
        buckets[
            f"{row.get('language') or 'unknown'}:{str(row.get('occurredAt') or '')[:7]}"
        ].append(row)
    selected: list[dict[str, Any]] = []
    while len(selected) < min(count, len(records)):
        for key in sorted(buckets):
            if buckets[key] and len(selected) < count:
                selected.append(buckets[key].pop())
    return selected


def summarize(rows: list[dict[str, Any]], total: int) -> dict[str, Any]:
    topics = Counter(row["result"]["topic"] for row in rows)
    sentiments = Counter(row["result"].get("sentiment") for row in rows)
    days: dict[str, Counter[str]] = defaultdict(Counter)
    ratings = [row["rating"] for row in rows if row.get("rating") is not None]
    for row in rows:
        if row.get("occurredAt"):
            day = str(row["occurredAt"])[:10]
            days[day]["total"] += 1
            days[day][row["result"]["topic"]] += 1
    return {
        "total": total,
        "processed": len(rows),
        "dated": sum(d["total"] for d in days.values()),
        "topics": dict(topics),
        "sentiments": {"unavailable" if k is None else k: v for k, v in sentiments.items()},
        "days": [{"date": day, **counts} for day, counts in sorted(days.items())],
        "ratingCount": len(ratings),
        "normalizedRatingMean": None
        if not ratings
        else sum((r["value"] - r["min"]) / (r["max"] - r["min"]) for r in ratings) / len(ratings),
        "inputTokens": sum(
            row["result"].get("inputTokens", 0)
            for row in rows
            if not row["result"].get("reusedFromRun")
        ),
        "outputTokens": sum(
            row["result"].get("outputTokens", 0)
            for row in rows
            if not row["result"].get("reusedFromRun")
        ),
        "reusedRecords": sum(bool(row["result"].get("reusedFromRun")) for row in rows),
        "exploratory": True,
        "protocol": PROTOCOL,
        "protocolHash": PROTOCOL_HASH,
    }


def trends(rows: list[dict[str, Any]], method: str) -> dict[str, Any]:
    if method not in ("simple_rate_change", "candidate_statistical"):
        raise ValueError("Unknown trend method")
    dated = [row for row in rows if row.get("occurredAt")]
    if not dated:
        return {"method": method, "reason": "no_dated_records", "candidates": []}
    counts: dict[date, Counter[str]] = defaultdict(Counter)
    for row in dated:
        day = date.fromisoformat(str(row["occurredAt"])[:10])
        counts[day]["total"] += 1
        counts[day][row["result"]["topic"]] += 1
    end = max(counts) + timedelta(days=1)
    config = DetectorConfig(
        version=f"workbench/{method}/1.0.0",
        current_days=7,
        baseline_days=28,
        min_current_eligible=10,
        min_baseline_eligible=20,
        min_current_positive=3,
        min_absolute_delta_pp=5,
        min_relative_change_percent=20,
        beta_prior_alpha=1 if method == "candidate_statistical" else None,
        beta_prior_beta=1 if method == "candidate_statistical" else None,
        min_probability_of_direction=0.95 if method == "candidate_statistical" else None,
    )
    detect = detect_rate_change if method == "simple_rate_change" else detect_beta_binomial_change
    candidates = []
    for topic in sorted({row["result"]["topic"] for row in dated}):
        observations = [
            DailyObservation(topic, day, c[topic], c["total"])
            for day, c in counts.items()
            if end - timedelta(days=35) <= day < end
        ]
        for direction in ("increase", "decrease"):
            result = detect(
                observations,
                series_id=topic,
                anchor=end,
                config=config,
                expected_direction=direction,
            )
            candidates.append(result.to_dict())
    return {
        "method": method,
        "analysisId": hashlib.sha256(
            json.dumps(
                {
                    "protocol": PROTOCOL_HASH,
                    "method": method,
                    "records": sorted(
                        (row["id"], row.get("occurredAt"), row["result"]["topic"]) for row in rows
                    ),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest(),
        "protocolHash": PROTOCOL_HASH,
        "exploratory": True,
        "candidates": candidates,
    }
