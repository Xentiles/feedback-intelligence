"""Verify ClickHouse projection boundaries using only a disposable local container.

Run with services/decision-worker/.venv/bin/python scripts/quality_projection_check.py.
The existing clickhouse/clickhouse-server:25.8 image is required; no image is pulled.
Synthetic eligible fixtures exist only inside this invocation's tmpfs database.
"""

from __future__ import annotations

import copy
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

from feedback_intelligence_worker.data.providers.synthetic import SyntheticDatasetProvider
from feedback_intelligence_worker.decision.envelope import build_decision_envelope
from feedback_intelligence_worker.decision.rules import RuleDecisionEngine
from feedback_intelligence_worker.decision.schema import load_decision_schema
from feedback_intelligence_worker.privacy import PrivacyBoundary
from feedback_intelligence_worker.storage.clickhouse import ClickHouseClient
from feedback_intelligence_worker.storage.events import (
    build_signal_projection_event,
    event_to_clickhouse_row,
)

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "disposable-projection-only"


def docker(*arguments: str) -> str:
    return subprocess.check_output(["docker", *arguments], text=True).strip()


def request(url: str, query: str, payload: bytes = b"", *, token: str | None = None) -> bytes:
    parameters = {"query": query}
    if token is not None:
        parameters["insert_deduplication_token"] = token
    message = urllib.request.Request(
        f"{url}/?{urllib.parse.urlencode(parameters)}",
        data=payload,
        headers={"X-ClickHouse-User": "quality", "X-ClickHouse-Key": PASSWORD},
        method="POST",
    )
    with urllib.request.urlopen(message, timeout=20) as response:
        return bytes(response.read())


def check(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def base_event() -> dict[str, Any]:
    record = SyntheticDatasetProvider(ROOT / "data/demo/feedback.jsonl").load_feedback().records[0]
    schema = load_decision_schema(ROOT / "schemas/feedback-decision/1.0.0/manifest.json")
    state = PrivacyBoundary().prepare_for_decision(record)
    envelope = build_decision_envelope(state, schema, RuleDecisionEngine().decide(state, schema))
    event = build_signal_projection_event(record, envelope)
    # Explicit test fixture: production uncalibrated eligibility remains unchanged.
    event["decision_time"] = "2026-01-06T10:00:00Z"
    event["eligibility"]["delivery_experience"] = True
    event["accepted_positive"]["delivery_experience"] = True
    event["policy"] = {"status": "active", "version": "test-policy-A"}
    event["provenance"]["model_version"] = "test-model-A"
    return event


def insert_row(url: str, row: dict[str, Any], *, token: str | None = None) -> None:
    request(
        url,
        "INSERT INTO feedback_intelligence.signal_facts FORMAT JSONEachRow",
        (json.dumps(row) + "\n").encode(),
        token=token or str(uuid4()),
    )


def new_row(base: dict[str, Any], **changes: object) -> dict[str, Any]:
    row = copy.deepcopy(base)
    row.update(
        projection_id=str(uuid4()),
        event_id=str(uuid4()),
        decision_id=str(uuid4()),
        **changes,
    )
    return row


def detector_counts(url: str) -> list[dict[str, Any]]:
    result = request(
        url,
        "SELECT model_version, policy_version, eligible_feedback, accepted_positive "
        "FROM feedback_intelligence.daily_detector_inputs "
        "ORDER BY model_version, policy_version FORMAT JSONEachRow",
    )
    rows: list[dict[str, Any]] = [json.loads(line) for line in result.splitlines()]
    for row in rows:
        row["eligible_feedback"] = int(row["eligible_feedback"])
        row["accepted_positive"] = int(row["accepted_positive"])
    return rows


def cohort(model: str, policy: str, positive: int) -> dict[str, Any]:
    return {
        "model_version": f"test-model-{model}",
        "policy_version": f"test-policy-{policy}",
        "eligible_feedback": 1,
        "accepted_positive": positive,
    }


def run_checks(url: str) -> None:
    client = ClickHouseClient(url, "quality", PASSWORD)
    for path in sorted((ROOT / "infra/clickhouse/migrations").glob("*.sql")):
        client.apply_migration(path)
    # Keep duplicate physical rows observable. FINAL and the detector view must
    # work without relying on background merges, exactly as during a retry.
    request(url, "SYSTEM STOP MERGES feedback_intelligence.signal_facts")
    event = base_event()
    base = event_to_clickhouse_row(event)
    client.insert_event(event)
    client.insert_event(event)  # Same payload after a simulated missing PostgreSQL ack.
    raw_query = "SELECT count() FROM feedback_intelligence.signal_facts"
    final_query = "SELECT count() FROM feedback_intelligence.signal_facts FINAL"
    check(client.scalar(raw_query), 1, "same-token replay physical facts")
    check(client.scalar(final_query), 1, "same-token replay FINAL facts")
    check(detector_counts(url), [cohort("A", "A", 1)], "same-token replay detector inputs")
    legacy_query = "SELECT sum(delivery_denominator) FROM feedback_intelligence.daily_signal_rollup"
    check(client.scalar(legacy_query), 2, "legacy rollup same-token replay inflation")
    print(
        "PASS: same-token replay: physical=1 FINAL=1 eligible=1 positive=1; legacy denominator=2",
        flush=True,
    )

    insert_row(url, base)  # New token models replay beyond the insert deduplication window.
    check(client.scalar(raw_query), 2, "forced replay physical facts")
    check(client.scalar(final_query), 1, "forced replay FINAL facts")
    check(detector_counts(url), [cohort("A", "A", 1)], "query-side projection deduplication")
    legacy_denominator = client.scalar(legacy_query)
    check(legacy_denominator, 3, "legacy insert-driven rollup inflation")
    print(
        "PASS: forced replay: physical=2 FINAL=1 eligible=1 positive=1; legacy denominator=3",
        flush=True,
    )

    insert_row(
        url,
        new_row(
            base,
            decision_time="2026-01-07 10:00:00.000",
            delivery_experience_accepted_positive=0,
        ),
    )
    check(detector_counts(url), [cohort("A", "A", 0)], "latest decision within cohort")
    insert_row(url, new_row(base, model_version="test-model-B"))
    insert_row(url, new_row(base, policy_version="test-policy-B"))
    expected = [cohort("A", "A", 0), cohort("A", "B", 1), cohort("B", "A", 1)]
    check(detector_counts(url), expected, "independent model and policy cohorts")
    check(client.scalar(final_query), 4, "accepted fixture logical facts")
    print("PASS: latest decisions/cohorts: FINAL=4 cohorts=3 eligible=3 positive=2", flush=True)

    excluded: list[dict[str, object]] = [
        {"policy_status": "uncalibrated"},
        {"policy_version": None},
        {"decision_time": None},
        {"source_provider_id": None},
        {"source_dataset_name": ""},
        {"source_dataset_version": None},
    ]
    for changes in excluded:
        insert_row(url, new_row(base, feedback_id=str(uuid4()), **changes))
    # Explicitly absent classification and ineligible signals also contribute nothing.
    insert_row(
        url, new_row(base, feedback_id=str(uuid4()), delivery_experience_accepted_positive=None)
    )
    insert_row(url, new_row(base, feedback_id=str(uuid4()), delivery_experience_eligible=0))
    check(
        detector_counts(url), expected, "uncalibrated/missing provenance/classification exclusion"
    )
    check(client.scalar(final_query), 12, "all synthetic fixture logical facts")
    check(client.scalar(raw_query), 13, "all synthetic fixture physical rows")
    print(
        "PASS: eight excluded facts: physical=13 FINAL=12 cohorts=3 eligible=3 positive=2",
        flush=True,
    )


def main() -> None:
    name = f"feedback-projection-quality-{uuid4().hex[:12]}"
    container_id = ""
    try:
        container_id = docker(
            "run",
            "--detach",
            "--rm",
            "--pull=never",
            "--name",
            name,
            "--label",
            "feedback-intelligence.quality=disposable",
            "--publish",
            "127.0.0.1::8123",
            "--tmpfs",
            "/var/lib/clickhouse",
            "--tmpfs",
            "/var/log/clickhouse-server",
            "--env",
            "CLICKHOUSE_USER=quality",
            "--env",
            f"CLICKHOUSE_PASSWORD={PASSWORD}",
            "--env",
            "CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1",
            "clickhouse/clickhouse-server:25.8",
        )
        port = docker("port", container_id, "8123/tcp").rsplit(":", 1)[1]
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 60
        while True:
            try:
                request(url, "SELECT 1")
                break
            except (urllib.error.URLError, ConnectionError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)
        run_checks(url)
    finally:
        if container_id:
            docker("rm", "--force", container_id)
            print(f"Removed disposable container {name}", flush=True)


if __name__ == "__main__":
    main()
