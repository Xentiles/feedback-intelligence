"""Operational HTTP errors must not expose response payloads."""

import io
from email.message import Message
from urllib.error import HTTPError

import pytest

from feedback_intelligence_worker.storage.clickhouse import ClickHouseClient


def test_http_failure_omits_sensitive_response_body(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = io.BytesIO(b"canary-provider-body@example.com")

    def fail(*args: object, **kwargs: object) -> None:
        raise HTTPError("http://local", 500, "private response reason", Message(), payload)

    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.raises(ValueError) as raised:
        ClickHouseClient("http://local", "test", "test").scalar("SELECT 1")
    assert str(raised.value) == "ClickHouse request failed (500)"
    assert raised.value.__suppress_context__
    assert payload.closed
