"""Minimal ClickHouse HTTP migration and idempotent projection client."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, cast

from feedback_intelligence_worker.storage.events import event_to_clickhouse_row


class ClickHouseClient:
    def __init__(self, url: str, user: str, password: str) -> None:
        self._url = url.rstrip("/")
        self._headers = {
            "X-ClickHouse-User": user,
            "X-ClickHouse-Key": password,
        }

    def apply_migration(self, path: Path) -> None:
        statements = [statement.strip() for statement in path.read_text().split(";")]
        for statement in statements:
            if statement:
                self._request(statement.encode(), {})

    def insert_event(self, event: dict[str, Any]) -> None:
        row = event_to_clickhouse_row(event)
        body = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        self._request(
            body,
            {
                "query": "INSERT INTO feedback_intelligence.signal_facts FORMAT JSONEachRow",
                "insert_deduplication_token": str(event["event_id"]),
            },
        )

    def scalar(self, query: str) -> int:
        response = self._request(b"", {"query": query, "default_format": "TabSeparated"})
        return int(response.decode().strip())

    def _request(self, body: bytes, parameters: dict[str, str]) -> bytes:
        query_string = urllib.parse.urlencode(parameters)
        request = urllib.request.Request(
            f"{self._url}/?{query_string}",
            data=body,
            headers=self._headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return cast(bytes, response.read())
        except urllib.error.HTTPError as error:
            error.close()
            raise ValueError(f"ClickHouse request failed ({error.code})") from None
