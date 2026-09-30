"""Bounded tabular imports. No formulas, external links, or fabricated timestamps."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import unicodedata
import zipfile
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

MAX_BYTES = 25 * 1024 * 1024
MAX_RECORDS = 10_000
MAX_TEXT = 20_000
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def depth(value: Any, level: int = 0) -> None:
    if level > 16:
        raise ValueError("JSON nesting exceeds 16 levels")
    if isinstance(value, dict):
        for item in value.values():
            depth(item, level + 1)
    elif isinstance(value, list):
        for item in value:
            depth(item, level + 1)


def parse_upload(content: bytes, filename: str, sheet: int = 0) -> dict[str, Any]:
    if len(content) > MAX_BYTES:
        raise ValueError("Upload exceeds 25 MiB")
    suffix = filename.rsplit(".", 1)[-1].lower()
    sheets: list[str] = []
    if suffix == "xlsx":
        rows, sheets = _xlsx(content, sheet)
    else:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError("Use UTF-8 text or an XLSX workbook") from error
        if suffix in ("json", "jsonl", "ndjson"):
            try:
                parsed = (
                    json.loads(text)
                    if suffix == "json"
                    else [json.loads(line) for line in text.splitlines() if line.strip()]
                )
                depth(parsed)
            except (RecursionError, json.JSONDecodeError) as error:
                raise ValueError("Invalid JSON or excessive nesting") from error
            if not isinstance(parsed, list) or any(not isinstance(row, dict) for row in parsed):
                raise ValueError(
                    "JSON must be an array of objects; JSONL requires one object per line"
                )
            rows = parsed
        elif suffix in ("csv", "tsv"):
            try:
                dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(io.StringIO(text), dialect=dialect)
            headers = reader.fieldnames or []
            if len(headers) != len(set(headers)) or any(not name for name in headers):
                raise ValueError("Column names must be non-empty and unique")
            rows = []
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("CSV row has a different number of cells than the header")
                rows.append(row)
                if len(rows) > MAX_RECORDS:
                    raise ValueError("Upload exceeds 10,000 records")
        elif suffix == "txt":
            rows = [{"text": line.strip()} for line in text.splitlines() if line.strip()]
        else:
            raise ValueError("Supported formats: CSV, TSV, XLSX, JSON, JSONL, TXT")
    if not rows or len(rows) > MAX_RECORDS:
        raise ValueError("Upload must contain 1-10,000 records")
    columns = list(dict.fromkeys(str(key) for row in rows for key in row))
    if len(columns) > 200:
        raise ValueError("Upload exceeds 200 columns")
    return {
        "rows": rows,
        "columns": columns,
        "sheets": sheets,
        "sourceHash": hashlib.sha256(content).hexdigest(),
        "filename": filename,
    }


def _xml(content: bytes) -> ET.Element:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Workbook XML must use UTF-8") from error
    if "<!DOCTYPE" in decoded.upper() or "<!ENTITY" in decoded.upper():
        raise ValueError("XML declarations and entities are unsupported")
    return ET.fromstring(decoded)


def _xlsx(content: bytes, sheet: int) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        entries = archive.infolist()
        if len(entries) > 1000 or sum(e.file_size for e in entries) > 100 * 1024 * 1024:
            raise ValueError("Workbook decompression limit exceeded")
        if any(e.file_size > 50 * 1024 * 1024 or e.flag_bits & 1 for e in entries):
            raise ValueError("Oversized or encrypted workbook entry")
        names = archive.namelist()
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
        target = next(r.get("Target", "") for r in rels if r.get("Id") == rid)
        if ".." in target or ":" in target:
            raise ValueError("Invalid worksheet location")
        path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            shared = ["".join(s.itertext()) for s in _xml(archive.read("xl/sharedStrings.xml"))]
        date_styles: set[int] = set()
        if "xl/styles.xml" in names:
            styles = _xml(archive.read("xl/styles.xml"))
            formats = {
                int(item.get("numFmtId", "0")): item.get("formatCode", "")
                for item in styles.findall("s:numFmts/s:numFmt", NS)
            }
            for index, item in enumerate(styles.findall("s:cellXfs/s:xf", NS)):
                code = int(item.get("numFmtId", "0"))
                custom = re.sub(r'"[^\"]*"|\[[^\]]*\]|\\.', "", formats.get(code, ""))
                if code in (*range(14, 23), *range(45, 48)) or re.search("[ymdhs]", custom, re.I):
                    date_styles.add(index)
        properties = workbook.find("s:workbookPr", NS)
        epoch = (
            datetime(1904, 1, 1)
            if properties is not None and properties.get("date1904") == "1"
            else datetime(1899, 12, 30)
        )
        table: list[dict[int, str]] = []
        for row in _xml(archive.read(path)).findall("s:sheetData/s:row", NS):
            cells: dict[int, str] = {}
            for cell in row:
                if cell.find("s:f", NS) is not None:
                    raise ValueError("Formula cells are unsupported; export values first")
                col = 0
                for char in cell.get("r", "").rstrip("0123456789"):
                    col = col * 26 + ord(char) - 64
                if not 1 <= col <= 200:
                    raise ValueError("Workbook column limit exceeded")
                value = cell.findtext("s:v", "", NS)
                if cell.get("t") == "s":
                    value = shared[int(value)]
                elif cell.get("t") == "inlineStr":
                    value = "".join(cell.find("s:is", NS).itertext())  # type: ignore[union-attr]
                elif int(cell.get("s", "0")) in date_styles and value:
                    serial = float(value)
                    if not math.isfinite(serial) or serial < 1 or serial > 2_900_000:
                        raise ValueError("Invalid spreadsheet date")
                    value = (epoch + timedelta(days=serial)).isoformat()
                cells[col - 1] = value
            table.append(cells)
            if len(table) > MAX_RECORDS + 1:
                raise ValueError("Workbook exceeds 10,000 records")
        if not table:
            raise ValueError("Selected sheet is empty")
        headers = [table[0].get(i, "") for i in range(max(table[0], default=-1) + 1)]
        if not headers or len(headers) != len(set(headers)) or any(not h for h in headers):
            raise ValueError("Sheet header must contain unique non-empty names")
        return [{h: row.get(i, "") for i, h in enumerate(headers)} for row in table[1:]], labels
    except (KeyError, StopIteration, IndexError, ET.ParseError, zipfile.BadZipFile) as error:
        raise ValueError("Invalid XLSX workbook") from error


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
                raise ValueError("Feedback exceeds 20,000 characters")
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
