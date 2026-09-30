"""Populate the local 10k rules scenario without any external inference."""

from __future__ import annotations

import http.cookiejar
import json
import time
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

    def call(path: str, body: object | None = None) -> object:
        request = urllib.request.Request(
            ORIGIN + "/api/v1/workbench" + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={
                "Origin": ORIGIN,
                "Content-Type": "application/json",
                "X-Workbench-CSRF": csrf,
            },
        )
        with client.open(request, timeout=90) as response:
            return json.load(response)

    session = call(
        "/session", {"code": (ROOT / ".workbench-runtime/api/owner-code").read_text().strip()}
    )
    assert isinstance(session, dict)
    csrf = session["csrf"]
    datasets = call("/datasets")
    assert isinstance(datasets, list)
    dataset = next(
        (
            d
            for d in datasets
            if d["name"] == "10,000 synthetic reviews - rules scenario" and d["status"] == "ready"
        ),
        None,
    )
    if dataset is None:
        dataset = call("/datasets/demo", {"count": 10000})
    assert isinstance(dataset, dict)
    templates = call("/templates")
    assert isinstance(templates, list)
    template = next(t for t in templates if t["name"] == "Retail feedback")
    runs = call("/runs")
    assert isinstance(runs, list)
    run = next(
        (
            r
            for r in runs
            if r["dataset_id"] == dataset["id"]
            and r["template_id"] == template["id"]
            and r["snapshot"]["engine"] == "rules"
            and r["status"] == "completed"
        ),
        None,
    )
    if run is None:
        run = call(
            "/runs",
            {
                "datasetId": dataset["id"],
                "templateId": template["id"],
                "engine": "rules",
                "idempotencyKey": str(uuid4()),
            },
        )
    elif isinstance(run, dict):
        previous = call("/runs/" + run["id"] + "/results")
        if (
            isinstance(previous, dict)
            and previous["rows"]
            and not previous["rows"][0]["result"].get("inputStateSha256")
        ):
            run = call(
                "/runs",
                {
                    "datasetId": dataset["id"],
                    "templateId": template["id"],
                    "engine": "rules",
                    "idempotencyKey": str(uuid4()),
                },
            )
    assert isinstance(run, dict)
    deadline = time.monotonic() + 600
    started = time.monotonic()
    while time.monotonic() < deadline:
        status = call("/runs/" + run["id"])
        assert isinstance(status, dict)
        if status["status"] == "completed":
            break
        if status["status"] in ("paused", "failed", "cancelled"):
            raise RuntimeError("Rules demo stopped; inspect Runs for its safe error codes")
        time.sleep(3)
    assert status["status"] == "completed" and status["succeeded"] == 10000, status
    results = call("/runs/" + run["id"] + "/results")
    assert isinstance(results, dict)
    assert results["summary"]["processed"] == 10000
    assert len(results["summary"]["days"]) == 450
    print(
        json.dumps(
            {
                "datasetId": dataset["id"],
                "runId": run["id"],
                "records": results["summary"]["processed"],
                "observedDays": len(results["summary"]["days"]),
                "topics": results["summary"]["topics"],
                "seconds": round(time.monotonic() - started, 2),
            }
        )
    )


if __name__ == "__main__":
    main()
