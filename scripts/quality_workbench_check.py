"""Local end-to-end workbench acceptance. Uses no provider credentials or paid calls."""

from __future__ import annotations

import base64
import http.cookiejar
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:8081"


def main() -> None:
    client = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    csrf = ""

    def call(path: str, data: object | None = None, method: str | None = None) -> object:
        request = urllib.request.Request(
            ORIGIN + "/api/v1/workbench" + path,
            data=None if data is None else json.dumps(data).encode(),
            method=method or ("GET" if data is None else "POST"),
            headers={
                "Content-Type": "application/json",
                "Origin": ORIGIN,
                "X-Workbench-CSRF": csrf,
            },
        )
        try:
            with client.open(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            message = json.load(error)
            detail = message.get("error", message.get("detail", "Request failed"))
            raise RuntimeError(f"{path}: HTTP {error.code}: {detail}") from None

    owner = (ROOT / ".workbench-runtime/api/owner-code").read_text().strip()
    session = call("/session", {"code": owner})
    assert isinstance(session, dict)
    csrf = session["csrf"]
    source = [
        {"text": "Great support person@example.test", "date": "2026-01-01T12:00:00Z"},
        {"text": "Poor quality. Please improve.", "date": None},
        {"text": "Neutral story", "date": "not-a-date"},
    ]
    preview = call(
        "/imports/preview",
        {
            "filename": "acceptance.json",
            "content": base64.b64encode(json.dumps(source).encode()).decode(),
        },
    )
    assert isinstance(preview, dict)
    options = {"mapping": {"text": "text", "date": "date"}, "language": "en"}
    validation = call("/imports/validate", {"uploadId": preview["uploadId"], "options": options})
    assert (
        isinstance(validation, dict)
        and validation["summary"]["accepted"] == 2
        and validation["summary"]["invalid"] == 1
    )
    assert "person@example.test" not in json.dumps(validation["privacyPreview"])
    dataset = call(
        "/imports/commit",
        {
            "uploadId": preview["uploadId"],
            "options": options,
            "name": "Acceptance-only dataset",
            "acceptExclusions": True,
        },
    )
    assert isinstance(dataset, dict)
    templates = call("/templates")
    assert isinstance(templates, list)
    template = next(t for t in templates if t["name"] == "General feedback")
    options_run = {
        "datasetId": dataset["id"],
        "templateId": template["id"],
        "engine": "rules",
        "idempotencyKey": str(uuid4()),
    }
    run = call("/runs", options_run)
    assert isinstance(run, dict)
    assert call("/runs", options_run)["id"] == run["id"]  # type: ignore[index]
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        status = call("/runs/" + run["id"])
        assert isinstance(status, dict)
        if status["status"] == "completed":
            break
        time.sleep(0.5)
    assert status["succeeded"] == 2 and status["failed"] == 0, status
    results = call("/runs/" + run["id"] + "/results")
    assert isinstance(results, dict) and results["summary"]["dated"] == 1
    assert "person@example.test" not in json.dumps(results)
    exported = call("/runs/" + run["id"] + "/export?format=json")
    assert isinstance(exported, dict) and "person@example.test" not in exported["content"]
    original = call("/runs/" + run["id"] + "/export?format=json&original=true")
    assert isinstance(original, dict) and "person@example.test" in original["content"]
    call("/datasets/" + dataset["id"], method="DELETE")
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        datasets = call("/datasets")
        assert isinstance(datasets, list)
        if not any(d["id"] == dataset["id"] for d in datasets):
            break
        time.sleep(0.5)
    assert not any(d["id"] == dataset["id"] for d in datasets), "Purge did not finish"
    print(
        "Workbench acceptance passed: upload, validation, idempotent rules run, "
        "privacy, evidence, export and durable purge"
    )


if __name__ == "__main__":
    main()
