"""Untrusted-file allocation, parser isolation, admission and retention regressions."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
import time
import zipfile
from typing import Any
from unittest.mock import patch

import pytest

from feedback_intelligence_worker.workbench import import_process, imports, server


@pytest.fixture(autouse=True)
def clean_previews() -> Any:
    server.UPLOADS.clear()
    server.UPLOAD_READERS.clear()
    server.UPLOAD_REMOVED.clear()
    yield
    server.UPLOADS.clear()
    server.UPLOAD_READERS.clear()
    server.UPLOAD_REMOVED.clear()


def upload(content: bytes = b"Great support", name: str = "a.txt") -> dict[str, Any]:
    return {"content": base64.b64encode(content).decode(), "filename": name}


@pytest.mark.parametrize("name", ["a.json", "a.jsonl", "a.ndjson"])
def test_nested_auxiliary_graph_rejected_before_decoder(name: str) -> None:
    row = '{"text":"feedback","unused":[' + "{}," * 19_999 + "{}]}"
    content = ("[" + row + "]" if name.endswith(".json") else row).encode()
    with (
        patch.object(json, "JSONDecoder", side_effect=AssertionError("late check")),
        pytest.raises(ValueError, match="nesting"),
    ):
        imports.parse_upload(content, name)


@pytest.mark.parametrize(
    ("content", "name"),
    [
        (b'[{"text":"a"},{"text":"b"},{"text":"c"}]', "a.json"),
        (b'{"text":"a"}\n{"text":"b"}\n{"text":"c"}', "a.jsonl"),
        (b'{"text":"a"}\n{"text":"b"}\n{"text":"c"}', "a.ndjson"),
        (b"a\nb\nc", "a.txt"),
        (b"text\na\nb\nc", "a.csv"),
    ],
)
def test_record_limit_checked_while_collecting(
    monkeypatch: pytest.MonkeyPatch, content: bytes, name: str
) -> None:
    monkeypatch.setattr(imports, "MAX_RECORDS", 2)
    with pytest.raises(ValueError, match="2 records"):
        imports.parse_upload(content, name)


def test_scalar_json_preserves_columns_unicode_hash_and_escaped_punctuation() -> None:
    content = json.dumps(
        [
            {"text": 'Åäö \\" [{}] : ,', "rating": 3, "date": None, "flag": True},
            {"text": "支持", "extra": "None"},
        ],
        ensure_ascii=False,
    ).encode()
    value = imports.parse_upload(b"\xef\xbb\xbf" + content, "DATA.JSON")
    assert value["columns"] == ["text", "rating", "date", "flag", "extra"]
    assert value["rows"][0]["flag"] is True and value["rows"][0]["date"] is None
    assert value["sourceHash"] == hashlib.sha256(b"\xef\xbb\xbf" + content).hexdigest()
    assert imports.parse_upload("a\rb\r\nc\u2028d\u0085e".encode(), "a.txt")["rows"] == [
        {"text": c} for c in "abcde"
    ]


@pytest.mark.parametrize(
    "content",
    [
        b'[{"text":"a", "text":"b"}]',
        b'[{"text":"a"},]',
        b'[{"x":NaN}]',
        '[\u00a0{"text":"a"}]'.encode(),
    ],
)
def test_malformed_and_ambiguous_json_rejected(content: bytes) -> None:
    with pytest.raises(ValueError):
        imports.parse_upload(content, "a.json")


def workbook(sheet: str, shared: str = "") -> bytes:
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{imports.NS["s"]}" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<workbookPr date1904="1"/><sheets><sheet name="Reviews" r:id="r1"/></sheets>'
            "</workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        if shared:
            archive.writestr("xl/sharedStrings.xml", shared)
    return result.getvalue()


def test_streamed_shared_strings_and_ignored_xml_sections() -> None:
    content = workbook(
        f'<worksheet xmlns="{imports.NS["s"]}"><sheetData>'
        '<row><c r="A1" t="s"><v>0</v></c></row>'
        '<row><c r="A2" t="s"><v>1</v></c></row></sheetData>'
        + "<ignored/>" * 10_000
        + "</worksheet>",
        f'<sst xmlns="{imports.NS["s"]}"><si><t>text</t></si>'
        "<si><r><t>Great </t></r><r><t>support</t></r></si></sst>",
    )
    assert imports.parse_upload(content, "a.xlsx")["rows"] == [{"text": "Great support"}]


def test_streamed_sheet_ignores_rows_outside_sheet_data() -> None:
    content = workbook(
        f'<worksheet xmlns="{imports.NS["s"]}">'
        '<extension><row><c r="A1" t="inlineStr"><is><t>wrong</t></is></c></row></extension>'
        '<sheetData><row><c r="A1" t="inlineStr"><is><t>text</t></is></c></row>'
        '<row><c r="A2" t="inlineStr"><is><t>right</t></is></c></row></sheetData></worksheet>'
    )
    assert imports.parse_upload(content, "a.xlsx")["rows"] == [{"text": "right"}]


def test_xml_structure_entities_and_bad_archives_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(imports, "MAX_XML_ELEMENTS", 20)
    content = workbook(
        f'<worksheet xmlns="{imports.NS["s"]}">' + "<unused/>" * 100 + "</worksheet>"
    )
    with pytest.raises(ValueError, match="structure"):
        imports.parse_upload(content, "a.xlsx")
    content = workbook('<!DOCTYPE x [<!ENTITY x "bad">]><worksheet/>')
    with pytest.raises(ValueError, match="entities"):
        imports.parse_upload(content, "a.xlsx")
    with pytest.raises(ValueError, match="Invalid XLSX"):
        imports.parse_upload(b"not a zip", "a.xlsx")


def test_retained_graph_budget_and_parent_recheck(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(imports, "MAX_PREVIEW_BYTES", 256)
    with pytest.raises(ValueError, match="Parsed preview"):
        imports.parse_upload(b"large text " * 100, "a.txt")
    with (
        patch.object(server, "isolated_parse", return_value={"rows": ["x" * 1000]}),
        pytest.raises(ValueError, match="Parsed preview"),
    ):
        server.preview_upload(upload())
    assert not server.UPLOADS


def test_shared_string_graph_transfer_is_bounded_before_parent_decoding() -> None:
    # XLSX can reuse one string across 900,000 cells. JSON duplicates those values:
    # a ~33 MiB child graph must not be accepted solely by its ~18 MiB wire size.
    row = {f"column{i}": "abcdefghij" for i in range(90)}
    graph = {"rows": [dict(row) for _ in range(10_000)], "columns": list(row)}
    imports.check_preview(graph)
    with pytest.raises(ValueError, match="Parsed preview"):
        imports.check_transfer(graph)


def test_cache_full_and_nonstring_content_rejected_before_parser() -> None:
    for i in range(4):
        server.UPLOADS[str(i)] = (time.monotonic() + 600, {})
    with (
        patch.object(server, "isolated_parse", side_effect=AssertionError("allocated early")),
        pytest.raises(server.ImportBusy),
    ):
        server.preview_upload(upload())
    with pytest.raises(ValueError, match="strings"):
        server.preview_upload({"content": {"huge": []}})


def test_simultaneous_previews_use_one_parser_and_release_failures() -> None:
    entered, finish = threading.Event(), threading.Event()
    failures: list[Exception] = []

    def slow(*_: Any) -> Any:
        entered.set()
        assert finish.wait(3)
        raise ValueError("Synthetic parser failure")

    def first() -> None:
        try:
            server.preview_upload(upload())
        except ValueError as error:
            failures.append(error)

    with patch.object(server, "isolated_parse", side_effect=slow) as parser:
        thread = threading.Thread(target=first)
        thread.start()
        assert entered.wait(3)
        try:
            with pytest.raises(server.ImportBusy):
                server.preview_upload(upload())
        finally:
            finish.set()
            thread.join(3)
        assert parser.call_count == 1 and len(failures) == 1
    assert server.PARSER_SLOT.acquire(blocking=False)
    server.PARSER_SLOT.release()


def test_expired_borrowed_preview_stays_counted_until_reader_releases() -> None:
    server.UPLOADS["held"] = (time.monotonic() + 600, {"rows": []})
    with server.borrowed_upload("held"):
        server.UPLOADS["held"] = (0, {"rows": []})
        with server.UPLOAD_LOCK:
            server.expire_uploads()
        assert "held" in server.UPLOADS
        with pytest.raises(ValueError, match="expired"), server.borrowed_upload("held"):
            pytest.fail("expired preview reused")
    assert not server.UPLOADS and not server.UPLOAD_READERS


def test_real_isolated_parser_preserves_legitimate_import_and_rejects_attack() -> None:
    value = import_process.isolated_parse(rb'[{"text":"Support \u00e5", "date":null}]', "a.json", 0)
    assert value["rows"] == [{"text": "Support å", "date": None}]
    with pytest.raises(ValueError, match="nesting"):
        import_process.isolated_parse(b'[{"text":"ok","extra":[{}]}]', "a.json", 0)


def test_isolated_child_timeout_is_killed_and_reaped(monkeypatch: pytest.MonkeyPatch) -> None:
    # A real child startup with an intentionally tiny deadline exercises kill/wait.
    monkeypatch.setattr(import_process, "PARSER_TIMEOUT_SECONDS", 0.000001)
    with pytest.raises(ValueError, match="30 seconds"):
        import_process.isolated_parse(b"a", "a.txt", 0)


def test_child_does_not_receive_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "credential-canary")
    monkeypatch.setenv("WORKBENCH_SERVICE_TOKEN", "broker-canary")
    original = subprocess.Popen
    environments: list[dict[str, str]] = []

    def launch(*args: Any, **kwargs: Any) -> Any:
        environments.append(kwargs["env"])
        return original(*args, **kwargs)

    with patch(
        "feedback_intelligence_worker.workbench.import_process.subprocess.Popen", side_effect=launch
    ):
        import_process.isolated_parse(b"feedback", "a.txt", 0)
    assert "OPENAI_API_KEY" not in environments[0]
    assert "WORKBENCH_SERVICE_TOKEN" not in environments[0]
    assert "canary" not in json.dumps(environments)


@pytest.mark.skipif(sys.platform != "linux", reason="Real address-space enforcement is Linux-only")
def test_real_child_memory_ceiling_rejects_allocation_without_killing_parent() -> None:
    code = (
        "import sys;from feedback_intelligence_worker.workbench import import_process as p;"
        "p.parse_upload=lambda *a: bytearray(p.PARSER_MEMORY_BYTES*2);"
        "sys.argv=['probe','a.txt','0'];p.main()"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        input=b"x",
        capture_output=True,
        timeout=10,
        env={k: v for k, v in os.environ.items() if k in ("PATH", "PYTHONPATH")},
    )
    assert result.returncode == 3 and result.stdout == b""
    assert import_process.isolated_parse(b"still usable", "a.txt", 0)["rows"] == [
        {"text": "still usable"}
    ]


def test_command_envelope_graph_budget_preserves_base64_string() -> None:
    imports.json_structure(json.dumps({"body": {"content": "{" * 100_001}}))
    with pytest.raises(ValueError, match="structure"):
        imports.json_structure('{"body":[' + "{}," * 50_001 + "{}]}")
