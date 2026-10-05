"""Observed facets and cohort inspection use saved decisions, never paid inference."""

from __future__ import annotations

import csv
import io
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from feedback_intelligence_worker.workbench.analysis import (
    DETECTOR_IMPLEMENTATION,
    PROTOCOL_HASH,
    filter_rows,
    normalize_filters,
    observed_facets,
    summarize,
    trends,
)
from feedback_intelligence_worker.workbench.server import handle


def saved_rows(count: int = 60) -> list[dict[str, Any]]:
    return [
        {
            "id": str(position),
            "position": position,
            "sourceId": f"source-{position}",
            "text": "Contact person@example.test about a product",
            "occurredAt": None
            if position % 10 == 0
            else (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=position % 4)).isoformat(),
            "language": "en" if position % 3 == 0 else "sv" if position % 3 == 1 else None,
            "rating": {"value": 4, "min": 1, "max": 5} if position % 2 else None,
            "groups": {"product": "None" if position % 3 == 0 else "__missing__"}
            if position % 3 != 2
            else {},
            "result": {
                "topic": "total"
                if position % 3 == 0
                else "date"
                if position % 3 == 1
                else "quality",
                "sentiment": "positive" if position % 3 != 2 else None,
                "redactedText": "Contact [email] about a product",
                "actionable": True,
                "requestedModel": "keywords-1.0.0",
                "resolvedModel": "keywords-1.0.0",
                "inputTokens": 0,
                "outputTokens": 0,
                "templateRevision": "template",
            },
        }
        for position in range(1, count + 1)
    ]


def template() -> dict[str, Any]:
    return {
        "name": "Editable topics",
        "topics": [
            {"id": "total", "label": "Total experience"},
            {"id": "date", "label": "Date scheduling"},
            {"id": "quality", "label": "Quality"},
            {"id": "unobserved", "label": "Configured but never observed"},
        ],
    }


class SavedSnapshot:
    calls = 0

    def __init__(self, _: str) -> None:
        pass

    def __enter__(self) -> SavedSnapshot:
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def result_snapshot(self, identity: str) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
        type(self).calls += 1
        return (
            {
                "id": identity,
                "target": 75,
                "succeeded": 60,
                "status": "paused",
                "snapshot": {
                    "template": template(),
                    "templateRevision": "template",
                    "datasetSnapshot": "dataset",
                    "protocolHash": PROTOCOL_HASH,
                },
            },
            saved_rows(),
            2,
        )


@pytest.fixture
def snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    SavedSnapshot.calls = 0
    monkeypatch.setattr("feedback_intelligence_worker.workbench.server.api_dsn", lambda: "fixture")
    monkeypatch.setattr("feedback_intelligence_worker.workbench.server.Repository", SavedSnapshot)


def test_facets_use_all_saved_successes_and_keep_literal_values_separate() -> None:
    rows = saved_rows()
    facets = observed_facets(rows, template())
    assert facets["topic"] == [
        {"value": "date", "label": "Date scheduling", "count": 20},
        {"value": "quality", "label": "Quality", "count": 20},
        {"value": "total", "label": "Total experience", "count": 20},
    ]
    assert facets["product"] == [
        {"value": "None", "label": "None", "count": 20},
        {"value": "__missing__", "label": "__missing__", "count": 20},
        {"value": None, "label": "Not supplied", "count": 20},
    ]
    assert facets["sentiment"][-1] == {"value": None, "label": "Unavailable", "count": 20}
    assert facets["group"] == [{"value": None, "label": "Not supplied", "count": 60}]
    literal = filter_rows(rows, normalize_filters({"product": ["None"]}))
    missing = filter_rows(rows, normalize_filters({"missing": ["product,sentiment"]}))
    assert len(literal) == len(missing) == 20
    assert not {row["id"] for row in literal} & {row["id"] for row in missing}


@pytest.mark.parametrize(
    "query,message",
    [
        ({"missing": ["topic"]}, "Missing-value filters"),
        ({"missing": ["product"], "product": ["None"]}, "either a value or missing"),
        ({"dateFrom": ["2026-1-1"]}, "YYYY-MM-DD"),
        ({"dateTo": ["2026-02-30"]}, "YYYY-MM-DD"),
        ({"dateFrom": ["2026-02-01"], "dateTo": ["2026-01-01"]}, "Start date"),
    ],
)
def test_invalid_cohort_filters_explain_correction(
    query: dict[str, list[str]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        normalize_filters(query)


def test_date_ranges_use_inclusive_utc_days_and_exclude_undated_records() -> None:
    rows = saved_rows(4)
    rows[0]["occurredAt"] = "2026-01-01T23:30:00-01:00"  # Jan 2 UTC
    rows[1]["occurredAt"] = "2026-01-02T01:00:00+02:00"  # Jan 1 UTC
    rows[2]["occurredAt"] = "2026-01-02T23:59:59+00:00"
    rows[3]["occurredAt"] = None
    selected = normalize_filters({"dateFrom": ["2026-01-02"], "dateTo": ["2026-01-02"]})
    assert [row["id"] for row in filter_rows(rows, selected)] == ["1", "3"]
    assert summarize(rows, 4)["dailySeries"][0]["total"] == 1


def test_reserved_topic_ids_cannot_overwrite_daily_metadata_or_counts() -> None:
    summary = summarize(saved_rows(), 75)
    assert summary["total"] == 75
    assert summary["processed"] == 60
    assert summary["dated"] == 54
    assert summary["ratingCount"] == 30
    assert summary["normalizedRatingMean"] == 0.75
    assert sum(day["total"] for day in summary["dailySeries"]) == 54
    assert all(sum(day["topics"].values()) == day["total"] for day in summary["dailySeries"])
    assert any(
        "date" in day["topics"] and "total" in day["topics"] for day in summary["dailySeries"]
    )
    assert all(isinstance(day["date"], str) for day in summary["days"])
    assert sum(day["total"] for day in summary["days"]) == 54


def test_results_snapshot_pagination_facets_and_summary_are_consistent(snapshot: None) -> None:
    results = handle("GET", "/runs/run/results", {}, {"page": ["999"]})
    assert results["page"] == 2 and results["pageSize"] == 50
    assert results["returned"] == 10 and results["filtered"] == 60
    assert len(results["rows"]) == 10
    assert results["summary"]["processed"] == 60
    assert results["run"]["succeeded"] == 60
    assert SavedSnapshot.calls == 1
    assert "person@example.test" not in json.dumps(results)
    filtered = handle("GET", "/runs/run/results", {}, {"topic": ["date"], "page": ["999"]})
    assert filtered["page"] == 1 and filtered["returned"] == 20
    assert filtered["filtered"] == filtered["summary"]["processed"] == 20
    assert len(filtered["facets"]["topic"]) == 3
    assert sum(option["count"] for option in filtered["facets"]["topic"]) == 60
    empty = handle("GET", "/runs/run/results", {}, {"product": ["absent"], "page": ["999"]})
    assert empty["page"] == 1 and empty["returned"] == empty["filtered"] == 0


def test_date_drilldown_results_and_exports_share_all_matching_records(snapshot: None) -> None:
    query = {"dateFrom": ["2026-01-02"], "dateTo": ["2026-01-03"], "page": ["999"]}
    results = handle("GET", "/runs/run/results", {}, query)
    document = json.loads(handle("GET", "/runs/run/export", {}, query)["content"])
    assert document["summary"] == results["summary"]
    assert {row["id"] for row in document["records"]} == {row["id"] for row in results["rows"]}
    assert document["filters"] == results["filters"]
    assert document["analysisImplementation"] == DETECTOR_IMPLEMENTATION
    assert document["originalTextIncluded"] is False
    assert "person@example.test" not in json.dumps(document)
    entire_export = json.loads(handle("GET", "/runs/run/export", {}, {"page": ["2"]})["content"])
    assert len(entire_export["records"]) == 60  # Export ignores pagination.
    original = handle("GET", "/runs/run/export", {}, {"original": ["true"]})
    assert "person@example.test" in original["content"]
    csv_export = handle("GET", "/runs/run/export", {}, {**query, "format": ["csv"]})
    csv_rows = list(csv.DictReader(io.StringIO(csv_export["content"])))
    assert len(csv_rows) == results["filtered"]
    assert json.loads(csv_rows[0]["filters"]) == results["filters"]
    assert csv_rows[0]["analysis_implementation"] == DETECTOR_IMPLEMENTATION


def test_trend_identity_preserves_cohort_and_rejects_topic_denominator(snapshot: None) -> None:
    with pytest.raises(ValueError, match="Clear the topic filter"):
        handle("GET", "/runs/run/trends", {}, {"topic": ["total"]})
    assert SavedSnapshot.calls == 0
    rows = saved_rows()
    analysis = trends(rows, "simple_rate_change")
    assert analysis["implementation"] == DETECTOR_IMPLEMENTATION
    assert analysis["protocolHash"] == PROTOCOL_HASH
    changed = trends(rows, "simple_rate_change", normalize_filters({"language": ["en"]}))
    assert changed["analysisId"] != analysis["analysisId"]
    assert (
        trends(list(reversed(rows)), "simple_rate_change")["analysisId"] == analysis["analysisId"]
    )
    renamed = deepcopy(rows)
    for row in renamed:
        if row["result"]["topic"] == "total":
            row["result"]["topic"] = "safe_name"
    renamed_analysis = trends(renamed, "simple_rate_change")
    reserved_candidates = [c for c in analysis["candidates"] if c["series_id"] == "total"]
    safe_candidates = [
        {**c, "series_id": "total"}
        for c in renamed_analysis["candidates"]
        if c["series_id"] == "safe_name"
    ]
    for reserved, safe in zip(reserved_candidates, safe_candidates, strict=True):
        assert reserved["current"] == safe["current"]
        assert reserved["baseline"] == safe["baseline"]
        assert reserved["current"]["eligible_count"] == 54
        assert reserved["current"]["accepted_count"] == 18
        assert reserved["delta_pp"] == safe["delta_pp"]
        assert reserved["status"] == safe["status"]
