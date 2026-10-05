"""Upload, privacy, rules, protocol and streaming regressions without live inference."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any
from unittest.mock import patch

import pytest

from feedback_intelligence_worker.privacy.models import PrivacyBoundaryError
from feedback_intelligence_worker.workbench.analysis import (
    builtin_templates,
    rule_classify,
    sample_records,
    summarize,
    trends,
    validate_template,
)
from feedback_intelligence_worker.workbench.imports import parse_upload, timestamp, validate_import
from feedback_intelligence_worker.workbench.openai import ProviderFailure, classify


def record(text: str = "Great support", **fields: Any) -> dict[str, Any]:
    return {
        "id": "13208892-0bbb-4ee6-90c6-ab6e69366298",
        "text": text,
        "language": "en",
        "channel": None,
        "occurredAt": None,
        "rating": None,
        "groups": {},
        **fields,
    }


def workbook(formula: bool = False) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Reviews" r:id="r1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row><c r="A1" t="inlineStr"><is><t>text</t></is></c></row>'
            '<row><c r="A2" t="inlineStr">'
            + ("<f>HYPERLINK()</f>" if formula else "")
            + "<is><t>Great support</t></is></c></row></sheetData></worksheet>",
        )
    return output.getvalue()


@pytest.mark.parametrize(
    ("content", "name"),
    [
        (b"text\nGreat support\n", "a.csv"),
        (b'[{"text":"Great support"}]', "a.json"),
        (b'{"text":"Great support"}\n', "a.jsonl"),
        (b"Great support\n", "a.txt"),
        (workbook(), "a.xlsx"),
    ],
)
def test_equivalent_imports_without_fabricated_dates(content: bytes, name: str) -> None:
    result = validate_import(parse_upload(content, name), {"mapping": {"text": "text"}})
    assert result["summary"]["accepted"] == 1
    assert result["records"][0]["text"] == "Great support"
    assert result["records"][0]["occurredAt"] is None


def test_duplicate_ids_reject_all_affected_rows_repeated_text_is_retained() -> None:
    source = parse_upload(b"id,text\na,hello\na,hello\nb,hello\nc,hello\n", "a.csv")
    result = validate_import(source, {"mapping": {"text": "text", "id": "id"}})
    assert result["summary"]["duplicateIds"] == 2
    assert result["summary"]["repeatedText"] == 3
    assert result["summary"]["accepted"] == 2


def test_invalid_rating_blank_text_and_invalid_date_are_reported() -> None:
    source = parse_upload(b"text,rating,date\nhello,6,\n,3,\nhello,3,not-a-date\n", "a.csv")
    result = validate_import(
        source,
        {
            "mapping": {"text": "text", "rating": "rating", "date": "date"},
            "ratingMin": 1,
            "ratingMax": 5,
        },
    )
    assert result["summary"]["invalid"] == 3
    assert result["summary"]["empty"] == 1


@pytest.mark.parametrize("day", ["2026-03-29T02:30:00", "2026-10-25T02:30:00"])
def test_dst_gap_and_overlap_rejected(day: str) -> None:
    with pytest.raises(ValueError, match="Ambiguous"):
        timestamp(day, "Europe/Stockholm")


def test_offset_dates_and_explicit_timezone() -> None:
    assert timestamp("2026-01-01T12:00:00+01:00", None) == "2026-01-01T11:00:00+00:00"
    with pytest.raises(ValueError, match="timezone"):
        timestamp("2026-01-01", None)


def test_formulas_and_excessive_json_depth_rejected() -> None:
    with pytest.raises(ValueError, match="Formula"):
        parse_upload(workbook(True), "a.xlsx")
    with pytest.raises(ValueError, match="nesting"):
        parse_upload(("[" * 18 + "0" + "]" * 18).encode(), "a.json")


def test_editable_rules_explain_precedence_redact_and_abstain() -> None:
    template = validate_template(builtin_templates()[0])
    classified = rule_classify(
        record("Great support, poor quality. Email person@example.test"), template
    )
    assert classified["topic"] == "service"
    assert classified["sentiment"] == "mixed"
    assert len(classified["matches"]) == 2
    assert "person@example.test" not in classified["redactedText"]
    assert rule_classify(record("Unrelated story", language="fr"), template)["sentiment"] is None
    assert rule_classify(record("Unrelated story"), template)["topic"] == "unclassified"
    with pytest.raises(PrivacyBoundaryError):
        rule_classify(record("Card number 4111 1111 1111 1111"), template)


def test_revision_and_sampling_are_stable() -> None:
    first = builtin_templates()[0]
    assert validate_template(first)["revision"] == validate_template(first)["revision"]
    first["topics"][0]["priority"] = 50
    assert (
        validate_template(first)["revision"]
        != validate_template(builtin_templates()[0])["revision"]
    )
    records = [record(id=str(i), language="en" if i % 2 else "sv") for i in range(80)]
    sample = sample_records(records)
    assert len(sample) == 25
    assert sample == sample_records(list(reversed(records)))
    assert {r["language"] for r in sample} == {"en", "sv"}


def test_summary_and_trends_do_not_invent_time_coverage() -> None:
    template = validate_template(builtin_templates()[0])
    rows = [{**record(), "result": rule_classify(record(), template)}]
    assert summarize(rows, 10)["processed"] == 1
    assert summarize(rows, 10)["dated"] == 0
    assert trends(rows, "simple_rate_change")["reason"] == "no_dated_records"
    rows[0]["occurredAt"] = "2026-01-31T12:00:00Z"
    assert all(
        r["status"] == "insufficient_coverage"
        for r in trends(rows, "candidate_statistical")["candidates"]
    )


def test_stream_requires_terminal_completion_and_no_secrets_in_output() -> None:
    template = validate_template(builtin_templates()[0])
    answer = {"topic": "service", "sentiment": "positive", "actionable": False}
    events = [
        {"type": "response.output_text.delta", "delta": json.dumps(answer)},
        {
            "type": "response.completed",
            "response": {
                "model": "resolved-model",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        },
    ]
    body = b"".join(b"data: " + json.dumps(event).encode() + b"\n" for event in events)
    captured: list[Any] = []

    def reply(request: Any, **_: Any) -> io.BytesIO:
        captured.append(request)
        return io.BytesIO(body)

    with patch("feedback_intelligence_worker.workbench.openai.urlopen", side_effect=reply):
        result = classify(
            record("support person@example.test"),
            template,
            "chosen-model",
            "secret-credential",
            lambda: True,
        )
    assert result["resolvedModel"] == "resolved-model"
    assert result["inputTokens"] == 10
    request_body = json.loads(captured[0].data)
    assert "reasoning" not in request_body
    assert result["reasoningEffort"] is None
    with patch("feedback_intelligence_worker.workbench.openai.urlopen", side_effect=reply):
        effort_result = classify(
            record(),
            template,
            "gpt-6.1-sol",
            "secret-credential",
            lambda: True,
            reasoning_effort="high",
        )
    assert json.loads(captured[-1].data)["reasoning"] == {"effort": "high"}
    assert effort_result["reasoningEffort"] == "high"
    assert request_body["store"] is False and request_body["stream"] is True
    assert "person@example.test" not in json.dumps(request_body)
    assert "secret-credential" not in json.dumps(result)
    with (
        patch(
            "feedback_intelligence_worker.workbench.openai.urlopen", return_value=io.BytesIO(b"")
        ),
        pytest.raises(ProviderFailure, match="interrupted"),
    ):
        classify(record(), template, "chosen-model", "secret-credential", lambda: True)


def test_usage_failure_after_streaming_pauses_run() -> None:
    events = (
        b'data: {"type":"response.failed","response":{"error":'
        b'{"code":"subscription_sharing_usage_limit_exceeded"}}}\n'
    )
    with (
        patch(
            "feedback_intelligence_worker.workbench.openai.urlopen", return_value=io.BytesIO(events)
        ),
        pytest.raises(ProviderFailure) as failure,
    ):
        classify(
            record(), validate_template(builtin_templates()[0]), "model", "secret", lambda: True
        )
    assert failure.value.pause
    assert failure.value.code == "subscription_sharing_usage_limit_exceeded"
