"""Bounded tabular imports. No formulas, external links, or fabricated timestamps."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import sys
import unicodedata
import zipfile
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo


def configured_limit(name: str, ceiling: int) -> int:
    value = int(os.getenv(name, str(ceiling)))
    if not 1 <= value <= ceiling:
        raise ValueError(f"{name} must be between 1 and {ceiling}")
    return value


MAX_BYTES = configured_limit("WORKBENCH_MAX_UPLOAD_BYTES", 25 * 1024 * 1024)
MAX_RECORDS = configured_limit("WORKBENCH_MAX_RECORDS", 10_000)
MAX_TEXT = configured_limit("WORKBENCH_MAX_TEXT_CHARS", 20_000)
MAX_PREVIEW_BYTES = 64 * 1024 * 1024
MAX_COLUMNS = 200
MAX_XML_ELEMENTS = 2_000_000
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


class PreviewBudget:
    """Account retained Python objects, including shared references, before caching."""

    def __init__(self, *, shared: bool = True) -> None:
        self.shared = shared
        self.seen: set[int] = set()
        self.total = 0

    def add(self, value: Any) -> None:
        identity = id(value)
        if self.shared:
            if identity in self.seen:
                return
            self.seen.add(identity)
        self.total += sys.getsizeof(value)
        if self.total > MAX_PREVIEW_BYTES:
            raise ValueError("Parsed preview exceeds 64 MiB; split the file or remove columns")
        if isinstance(value, dict):
            for key, item in value.items():
                self.add(key)
                self.add(item)
        elif isinstance(value, list):
            for item in value:
                self.add(item)


def check_preview(value: dict[str, Any]) -> None:
    PreviewBudget().add(value)


def check_transfer(value: dict[str, Any]) -> None:
    # JSON loses shared strings. Count every occurrence before writing output so
    # parent deserialization cannot reconstruct an oversized graph before checking.
    # Counting shared keys/primitives again is deliberately conservative.
    PreviewBudget(shared=False).add(value)


def json_structure(text: str, *, table: bool = False, array: bool = True) -> None:
    """Bound JSON structure without deserializing a second object graph.

    Strings are skipped lexically; the JSON decoder remains grammar authority.
    Table mode allows only a top-level row array and scalar-valued row objects.
    General mode protects the internal command envelope before json.loads.
    """
    stack: list[str] = []
    index = rows = columns = tokens = 0
    while index < len(text):
        char = text[index]
        if char == '"':
            index += 1
            while index < len(text):
                if text[index] == "\\":
                    index += 2
                elif text[index] == '"':
                    index += 1
                    break
                else:
                    index += 1
            continue
        if char in "[{":
            if table:
                allowed = (array and not stack and char == "[") or (
                    char == "{" and stack == (["["] if array else [])
                )
                if not allowed:
                    raise ValueError("JSON nesting is unsupported; use scalar tabular cells")
                if char == "{":
                    rows += 1
                    columns = 0
                    if rows > MAX_RECORDS:
                        raise ValueError(f"Upload exceeds {MAX_RECORDS} records")
            stack.append(char)
            if len(stack) > 16:
                raise ValueError("JSON nesting exceeds 16 levels")
            tokens += 1
        elif char in "]}":
            if not stack or stack.pop() != ("[" if char == "]" else "{"):
                raise ValueError("Invalid JSON structure")
        elif char in ",:":
            tokens += 1
            if table and char == ":":
                columns += 1
                if columns > MAX_COLUMNS:
                    raise ValueError("Upload exceeds 200 columns")
        if not table and tokens > 100_000:
            raise ValueError("Request JSON structure exceeds limit")
        index += 1
    if stack:
        raise ValueError("Invalid JSON structure")


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, value in pairs:
        if key in row:
            raise ValueError("JSON column names must be unique")
        if isinstance(value, (dict, list)):
            raise ValueError("JSON nesting is unsupported; use scalar tabular cells")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        row[key] = value
    return row


def _invalid_constant(_: str) -> Any:
    raise ValueError("JSON numbers must be finite")


def _json_rows(text: str) -> Iterator[dict[str, Any]]:
    json_structure(text, table=True)
    decoder = json.JSONDecoder(object_pairs_hook=_json_object, parse_constant=_invalid_constant)
    index = 0
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    if index >= len(text) or text[index] != "[":
        raise ValueError("JSON must be an array of objects")
    index += 1
    first = True
    while True:
        while index < len(text) and text[index] in " \t\r\n":
            index += 1
        if index < len(text) and text[index] == "]":
            if not first:
                raise ValueError("JSON array has a trailing comma")
            index += 1
            break
        row, index = decoder.raw_decode(text, index)
        if not isinstance(row, dict):
            raise ValueError("JSON must be an array of objects")
        yield row
        while index < len(text) and text[index] in " \t\r\n":
            index += 1
        if index < len(text) and text[index] == "]":
            index += 1
            break
        if index >= len(text) or text[index] != ",":
            raise ValueError("Invalid JSON array")
        index += 1
        first = False
    if text[index:].strip(" \t\r\n"):
        raise ValueError("Unexpected content after JSON array")


def _lines(text: str, *, strip: bool = True) -> Iterator[str]:
    # Preserve splitlines' CR/CRLF and Unicode separators without a full line list.
    for match in re.finditer(r"[^\n\r\v\f\x1c-\x1e\x85\u2028\u2029]+", text):
        line = match.group()
        if line.strip():
            yield line.strip() if strip else line


def parse_upload(content: bytes, filename: str, sheet: int = 0) -> dict[str, Any]:
    if len(content) > MAX_BYTES:
        raise ValueError(f"Upload exceeds the configured {MAX_BYTES}-byte limit")
    suffix = filename.rsplit(".", 1)[-1].lower()
    sheets: list[str] = []
    rows: list[dict[str, Any]] = []
    columns: dict[str, None] = {}
    budget = PreviewBudget()

    def retain(row: dict[str, Any]) -> None:
        if len(rows) >= MAX_RECORDS:
            raise ValueError(f"Upload exceeds {MAX_RECORDS} records")
        for key in row:
            columns[key] = None
            if len(columns) > MAX_COLUMNS:
                raise ValueError("Upload exceeds 200 columns")
        budget.add(row)
        rows.append(row)

    try:
        if suffix == "xlsx":
            stream, sheets = _xlsx(content, sheet)
            for row in stream:
                retain(row)
        else:
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError as error:
                raise ValueError("Use UTF-8 text or an XLSX workbook") from error
            if suffix == "json":
                for row in _json_rows(text):
                    retain(row)
            elif suffix in ("jsonl", "ndjson"):
                for line in _lines(text, strip=False):
                    if len(rows) >= MAX_RECORDS:
                        raise ValueError(f"Upload exceeds {MAX_RECORDS} records")
                    json_structure(line, table=True, array=False)
                    row = json.loads(
                        line, object_pairs_hook=_json_object, parse_constant=_invalid_constant
                    )
                    if not isinstance(row, dict):
                        raise ValueError("JSONL requires one object per line")
                    retain(row)
            elif suffix in ("csv", "tsv"):
                try:
                    dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
                except csv.Error:
                    dialect = csv.excel
                reader = csv.DictReader(io.StringIO(text), dialect=dialect)
                headers = reader.fieldnames or []
                if len(headers) > MAX_COLUMNS:
                    raise ValueError("Upload exceeds 200 columns")
                if len(headers) != len(set(headers)) or any(not name for name in headers):
                    raise ValueError("Column names must be non-empty and unique")
                for row in reader:
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError("CSV row has a different number of cells than the header")
                    retain(row)
            elif suffix == "txt":
                for line in _lines(text):
                    retain({"text": line})
            else:
                raise ValueError("Supported formats: CSV, TSV, XLSX, JSON, JSONL, TXT")
    except (RecursionError, json.JSONDecodeError) as error:
        raise ValueError("Invalid JSON or excessive nesting") from error
    if not rows:
        raise ValueError(f"Upload must contain 1-{MAX_RECORDS} records")
    value = {
        "rows": rows,
        "columns": list(columns),
        "sheets": sheets,
        "sourceHash": hashlib.sha256(content).hexdigest(),
        "filename": filename,
    }
    check_preview(value)
    return value


def _xml(content: bytes) -> ET.Element:
    if len(content) > 1024 * 1024:
        raise ValueError("Workbook metadata exceeds 1 MiB")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Workbook XML must use UTF-8") from error
    if "<!DOCTYPE" in decoded.upper() or "<!ENTITY" in decoded.upper():
        raise ValueError("XML declarations and entities are unsupported")
    return ET.fromstring(decoded)


class _XmlReader(io.TextIOBase):
    def __init__(self, source: io.TextIOWrapper) -> None:
        self.source = source
        self.tail = ""

    def read(self, size: int | None = -1) -> str:
        try:
            value = self.source.read(size)
        except UnicodeDecodeError as error:
            raise ValueError("Workbook XML must use UTF-8") from error
        combined = (self.tail + value).upper()
        if "<!DOCTYPE" in combined or "<!ENTITY" in combined:
            raise ValueError("XML declarations and entities are unsupported")
        self.tail = combined[-16:]
        return value


def _xml_elements(
    archive: zipfile.ZipFile, path: str, tag: str, ancestors: tuple[str, ...]
) -> Iterator[ET.Element]:
    stack: list[ET.Element] = []
    selected = count = 0
    with archive.open(path) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig") as source:
        for event, element in ET.iterparse(_XmlReader(source), events=("start", "end")):
            if event == "start":
                stack.append(element)
                count += 1
                if count > MAX_XML_ELEMENTS or len(stack) > 32:
                    raise ValueError("Workbook XML structure exceeds limit")
                if (
                    element.tag == tag
                    and not selected
                    and tuple(parent.tag for parent in stack[:-1]) == ancestors
                ):
                    selected = len(stack)
            else:
                if len(stack) == selected:
                    yield element
                    selected = 0
                if not selected:
                    if len(stack) > 1:
                        stack[-2].remove(element)
                    element.clear()
                stack.pop()


def _xlsx(content: bytes, sheet: int) -> tuple[Iterator[dict[str, Any]], list[str]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise ValueError("Invalid XLSX workbook") from None
    try:
        entries = archive.infolist()
        if len(entries) > 1000 or sum(e.file_size for e in entries) > 100 * 1024 * 1024:
            raise ValueError("Workbook decompression limit exceeded")
        if any(e.file_size > 50 * 1024 * 1024 or e.flag_bits & 1 for e in entries):
            raise ValueError("Oversized or encrypted workbook entry")
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Workbook entries must be unique")
        if any("vba" in name.lower() or "externallinks" in name.lower() for name in names):
            raise ValueError("Macros and external links are unsupported")
        workbook = _xml(archive.read("xl/workbook.xml"))
        sheets = workbook.findall("s:sheets/s:sheet", NS)
        labels = [s.get("name", "") for s in sheets]
        if not 0 <= sheet < len(sheets):
            raise ValueError("Select an existing sheet")
        rels = _xml(archive.read("xl/_rels/workbook.xml.rels"))
        rid = sheets[sheet].get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        relation = next(r for r in rels if r.get("Id") == rid)
        if relation.get("TargetMode") == "External":
            raise ValueError("External worksheet links are unsupported")
        target = relation.get("Target", "")
        if ".." in target or ":" in target:
            raise ValueError("Invalid worksheet location")
        path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
        shared: list[str] = []
        shared_budget = PreviewBudget()
        if "xl/sharedStrings.xml" in names:
            for element in _xml_elements(
                archive, "xl/sharedStrings.xml", f"{{{NS['s']}}}si", (f"{{{NS['s']}}}sst",)
            ):
                value = "".join(element.itertext())
                shared_budget.add(value)
                shared.append(value)
                if len(shared) > 200 * (MAX_RECORDS + 1):
                    raise ValueError("Workbook shared string limit exceeded")
        date_styles: set[int] = set()
        if "xl/styles.xml" in names:
            styles = _xml(archive.read("xl/styles.xml"))
            formats = {
                _workbook_integer(item.get("numFmtId", "0")): item.get("formatCode", "")
                for item in styles.findall("s:numFmts/s:numFmt", NS)
            }
            for index, item in enumerate(styles.findall("s:cellXfs/s:xf", NS)):
                code = _workbook_integer(item.get("numFmtId", "0"))
                custom = re.sub(r'"[^\"]*"|\[[^\]]*\]|\\.', "", formats.get(code, ""))
                if code in (*range(14, 23), *range(45, 48)) or re.search("[ymdhs]", custom, re.I):
                    date_styles.add(index)
        properties = workbook.find("s:workbookPr", NS)
        epoch = (
            datetime(1904, 1, 1)
            if properties is not None and properties.get("date1904") == "1"
            else datetime(1899, 12, 30)
        )
    except (KeyError, StopIteration, ET.ParseError, zipfile.BadZipFile):
        archive.close()
        raise ValueError("Invalid XLSX workbook") from None
    except Exception:
        archive.close()
        raise

    def records() -> Iterator[dict[str, Any]]:
        headers: list[str] | None = None
        try:
            with archive:
                for position, row in enumerate(
                    _xml_elements(
                        archive,
                        path,
                        f"{{{NS['s']}}}row",
                        (f"{{{NS['s']}}}worksheet", f"{{{NS['s']}}}sheetData"),
                    )
                ):
                    if position > MAX_RECORDS:
                        raise ValueError(f"Workbook exceeds {MAX_RECORDS} records")
                    cells: dict[int, str] = {}
                    for cell in row:
                        if cell.find("s:f", NS) is not None:
                            raise ValueError("Formula cells are unsupported; export values first")
                        col = 0
                        for char in cell.get("r", "").rstrip("0123456789"):
                            if not "A" <= char <= "Z":
                                raise ValueError("Invalid workbook cell location")
                            col = col * 26 + ord(char) - 64
                            if col > MAX_COLUMNS:
                                raise ValueError("Workbook column limit exceeded")
                        if not 1 <= col <= MAX_COLUMNS or col - 1 in cells:
                            raise ValueError("Invalid or duplicate workbook cell location")
                        value = cell.findtext("s:v", "", NS)
                        if cell.get("t") == "s":
                            value = shared[_workbook_integer(value)]
                        elif cell.get("t") == "inlineStr":
                            inline = cell.find("s:is", NS)
                            if inline is None:
                                raise ValueError("Invalid inline workbook text")
                            value = "".join(inline.itertext())
                        elif _workbook_integer(cell.get("s", "0")) in date_styles and value:
                            try:
                                serial = float(value)
                            except ValueError:
                                raise ValueError("Invalid spreadsheet date") from None
                            if not math.isfinite(serial) or serial < 1 or serial > 2_900_000:
                                raise ValueError("Invalid spreadsheet date")
                            value = (epoch + timedelta(days=serial)).isoformat()
                        cells[col - 1] = value
                    if headers is None:
                        headers = [cells.get(i, "") for i in range(max(cells, default=-1) + 1)]
                        if (
                            not headers
                            or len(headers) != len(set(headers))
                            or any(not h for h in headers)
                        ):
                            raise ValueError("Sheet header must contain unique non-empty names")
                    else:
                        yield {h: cells.get(i, "") for i, h in enumerate(headers)}
                if headers is None:
                    raise ValueError("Selected sheet is empty")
        except (KeyError, StopIteration, IndexError, ET.ParseError, zipfile.BadZipFile) as error:
            raise ValueError("Invalid XLSX workbook") from error

    return records(), labels


def _workbook_integer(value: str) -> int:
    if not value.isascii() or not value.isdigit() or len(value) > 9:
        raise ValueError("Invalid workbook numeric field")
    return int(value)


def timestamp(value: str, timezone: str | None) -> str | None:
    if not value.strip():
        return None
    try:
        try:
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Invalid date; use ISO 8601") from None
        if date.tzinfo is None:
            if not timezone:
                raise ValueError("Choose a timezone for dates without an offset")
            zone = ZoneInfo(timezone)
            first, second = date.replace(tzinfo=zone, fold=0), date.replace(tzinfo=zone, fold=1)
            if (
                first.utcoffset() != second.utcoffset()
                or first.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != date
            ):
                raise ValueError("Ambiguous or nonexistent local date; supply an explicit offset")
            date = first
        return date.astimezone(UTC).isoformat()
    except (TypeError, OverflowError) as error:
        raise ValueError("Invalid date") from error


def validate_import(upload: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    mapping = options.get("mapping", {})
    if not isinstance(mapping, dict) or mapping.get("text") not in upload["columns"]:
        raise ValueError("Map the feedback text column")
    if any(value and value not in upload["columns"] for value in mapping.values()):
        raise ValueError("Mapped column is absent")
    snapshot = hashlib.sha256(
        json.dumps([upload["sourceHash"], options], sort_keys=True).encode()
    ).hexdigest()
    rows = upload["rows"]
    ids = [str(row.get(mapping.get("id")) or "").strip() for row in rows]
    counts = Counter(i for i in ids if i)
    texts = Counter(normalize(str(row.get(mapping["text"], ""))) for row in rows)
    accepted: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    duplicate_ids = empty = missing_dates = 0
    for position, row in enumerate(rows, start=1):
        try:
            source_id = ids[position - 1]
            if not source_id:
                source_id = f"generated-row-{position}"
                while source_id in counts:
                    source_id = "_" + source_id
            if counts[source_id] > 1:
                duplicate_ids += 1
                raise ValueError("Duplicate source ID")
            raw = row.get(mapping["text"])
            if not isinstance(raw, str) or not raw.strip():
                empty += 1
                raise ValueError("Feedback text is empty or is not a string")
            if len(raw) > MAX_TEXT:
                raise ValueError(f"Feedback exceeds the configured {MAX_TEXT}-character limit")
            date = timestamp(str(row.get(mapping.get("date"), "") or ""), options.get("timezone"))
            missing_dates += int(date is None)
            rating = None
            if (
                mapping.get("rating")
                and row.get(mapping["rating"]) is not None
                and str(row.get(mapping["rating"], "")).strip()
            ):
                minimum, maximum = (
                    float(options.get("ratingMin", 1)),
                    float(options.get("ratingMax", 5)),
                )
                try:
                    value = float(row[mapping["rating"]])
                except (TypeError, ValueError):
                    raise ValueError("Rating must be numeric") from None
                if (
                    not all(math.isfinite(v) for v in (minimum, maximum, value))
                    or not minimum <= value <= maximum
                    or minimum >= maximum
                ):
                    raise ValueError("Rating is outside its declared scale")
                rating = {"value": value, "min": minimum, "max": maximum}
            accepted.append(
                {
                    "schemaVersion": "workbench-record/1.0.0",
                    "id": str(uuid5(NAMESPACE_URL, f"{snapshot}:{source_id}")),
                    "position": position,
                    "sourceId": source_id,
                    "text": raw,
                    "occurredAt": date,
                    "language": str(
                        row.get(mapping.get("language"), "") or options.get("language", "")
                    ).strip()
                    or None,
                    "channel": str(row.get(mapping.get("channel"), "") or "").strip() or None,
                    "rating": rating,
                    "groups": {
                        key: str(row[value])
                        for key, value in mapping.items()
                        if key in ("product", "group") and value and row.get(value) is not None
                    },
                }
            )
        except (ValueError, KeyError, TypeError) as error:
            issues.append(
                {
                    "row": position,
                    "message": str(error)
                    if isinstance(error, ValueError)
                    else "Invalid mapped field",
                }
            )
    return {
        "snapshot": snapshot,
        "records": accepted,
        "summary": {
            "total": len(rows),
            "accepted": len(accepted),
            "invalid": len(issues),
            "empty": empty,
            "duplicateIds": duplicate_ids,
            "repeatedText": sum(n - 1 for t, n in texts.items() if t),
            "missingDates": missing_dates,
        },
        "issues": issues,
    }
