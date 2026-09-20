"""Check lease and persistence boundaries in a disposable local PostgreSQL container.

Run from the repository root:
    services/decision-worker/.venv/bin/python scripts/quality_storage_check.py

Uses the already-installed postgres:18-alpine image, a random loopback port and
tmpfs data. It never reads application connection settings or connects to an
existing database. Only the container created by this invocation is removed.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any
from uuid import uuid4

import psycopg
from feedback_intelligence_worker.data.providers.synthetic import SyntheticDatasetProvider
from feedback_intelligence_worker.decision.envelope import build_decision_envelope
from feedback_intelligence_worker.decision.rules import RuleDecisionEngine
from feedback_intelligence_worker.decision.schema import load_decision_schema
from feedback_intelligence_worker.privacy import PrivacyBoundary
from feedback_intelligence_worker.storage.events import build_signal_projection_event
from feedback_intelligence_worker.storage.repository import StorageRepository
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
Connection = psycopg.Connection[dict[str, Any]]


def docker(*arguments: str) -> str:
    return subprocess.check_output(["docker", *arguments], text=True).strip()


def check(condition: bool, description: str) -> None:
    if not condition:
        raise AssertionError(description)


def row(connection: Connection, table: str, identity: str) -> dict[str, Any]:
    key = "job_id" if table == "processing_jobs" else "event_id"
    result = connection.execute(
        psycopg.sql.SQL("SELECT * FROM feedback.{} WHERE {} = %s").format(
            psycopg.sql.Identifier(table), psycopg.sql.Identifier(key)
        ),
        (identity,),
    ).fetchone()
    assert result is not None
    return result


def seed(
    connection: Connection,
    kind: str,
    feedback_id: str,
    *,
    attempts: int = 0,
    maximum: int = 2,
    active: bool = False,
    expired: bool = True,
) -> str:
    identity = str(uuid4())
    if kind == "job":
        connection.execute(
            """INSERT INTO feedback.processing_jobs
               (job_id, idempotency_key, feedback_id, decision_schema_name,
                decision_schema_version, decision_schema_sha256, engine, requested_model,
                attempt_count, max_attempts, status, leased_until, lease_token, lease_owner)
               VALUES (%s, %s, %s, 'feedback-decision', '1.0.0', %s, 'rules', 'rules-1.0.0',
                       %s, %s, %s, clock_timestamp() + (%s * interval '1 hour'), %s, 'old')""",
            (
                identity,
                identity,
                feedback_id,
                "sha256:" + "0" * 64,
                attempts,
                maximum,
                "running" if active else "pending",
                -1 if expired else 1,
                uuid4(),
            ),
        )
    else:
        connection.execute(
            """INSERT INTO feedback.outbox_events
               (event_id, event_type, event_version, aggregate_id, payload,
                attempt_count, max_attempts, status, leased_until, lease_token, lease_owner)
               VALUES (%s, 'signal.projection.requested', 'signal-projection-event/1.1.0',
                       %s, %s, %s, %s, %s,
                       clock_timestamp() + (%s * interval '1 hour'), %s, 'old')""",
            (
                identity,
                uuid4(),
                Jsonb({"projection_id": str(uuid4())}),
                attempts,
                maximum,
                "publishing" if active else "pending",
                -1 if expired else 1,
                uuid4(),
            ),
        )
    return identity


def check_exhaustion(
    connection: Connection, repository: StorageRepository, feedback_id: str
) -> None:
    for kind, table, claim, fail, default_limit in (
        ("job", "processing_jobs", repository.claim_job, repository.persist_failure, 5),
        (
            "event",
            "outbox_events",
            repository.claim_event,
            repository.persist_projection_failure,
            8,
        ),
    ):
        active_id = seed(
            connection, kind, feedback_id, attempts=2, maximum=2, active=True, expired=False
        )
        before = row(connection, table, active_id)
        check(claim("live-owner-check") is None, "nonexpired exhausted owner was claimed")
        check(row(connection, table, active_id) == before, "live exhausted owner was changed")
        connection.execute(
            psycopg.sql.SQL("UPDATE feedback.{} SET status = 'dead'").format(
                psycopg.sql.Identifier(table)
            )
        )

        for attempts, maximum, expected in (
            (0, 1, "dead"),
            (default_limit - 1, default_limit + 1, "retry_wait"),
            (default_limit, default_limit + 1, "dead"),
        ):
            identity = seed(connection, kind, feedback_id, attempts=attempts, maximum=maximum)
            claimed = claim("configured-limit-check")
            assert claimed is not None
            private_canary = "private-customer@example.invalid secret-key-quality-canary"
            fail(claimed, ValueError(private_canary))  # type: ignore[arg-type]
            failure = row(connection, table, identity)
            check(failure["last_error_code"] == "ValueError", "failure lost its error class")
            check(
                all(value not in failure["last_error_message"] for value in private_canary.split()),
                f"{kind}: persisted private exception text",
            )
            check(
                row(connection, table, identity)["status"] == expected,
                f"{kind}: configured maximum was ignored",
            )
            connection.execute(
                psycopg.sql.SQL("UPDATE feedback.{} SET status = 'dead'").format(
                    psycopg.sql.Identifier(table)
                )
            )
    print("PASS: nonexpired ownership, configured attempt limits, safe error messages", flush=True)


def check_concurrent_claims(dsn: str, connection: Connection, feedback_id: str) -> None:
    for kind in ("job", "event"):
        identities = {seed(connection, kind, feedback_id) for _ in range(4)}
        barrier = Barrier(4)

        def claim_one(index: int, barrier: Barrier = barrier, kind: str = kind) -> str:
            with StorageRepository(dsn) as repository:
                barrier.wait(timeout=10)
                if kind == "job":
                    job = repository.claim_job(f"concurrent-{index}")
                    assert job is not None
                    repository.persist_failure(job, ValueError("synthetic"))
                    return job.job_id
                event = repository.claim_event(f"concurrent-{index}")
                assert event is not None
                repository.persist_projection_failure(event, ValueError("synthetic"))
                return event.event_id

        with ThreadPoolExecutor(max_workers=4) as executor:
            claimed_ids = list(executor.map(claim_one, range(4)))
        check(
            len(set(claimed_ids)) == 4 and set(claimed_ids) == identities,
            f"{kind}: concurrent claims did not have unique owners",
        )
        table = "processing_jobs" if kind == "job" else "outbox_events"
        connection.execute(
            psycopg.sql.SQL("UPDATE feedback.{} SET status = 'dead'").format(
                psycopg.sql.Identifier(table)
            )
        )
    print("PASS: concurrent job and outbox claim uniqueness", flush=True)


def expect_lost_lease(operation: Callable[[], None]) -> None:
    try:
        operation()
    except ValueError as error:
        check("lease was lost" in str(error), "unexpected persistence error")
    else:
        raise AssertionError("stale owner committed")


def check_transactions(
    connection: Connection, repository: StorageRepository, feedback_id: str
) -> None:
    seed(connection, "job", feedback_id)
    old_job = repository.claim_job("old-job-owner")
    assert old_job is not None
    connection.execute(
        "UPDATE feedback.processing_jobs "
        "SET leased_until = clock_timestamp() - interval '1 second' "
        "WHERE job_id = %s",
        (old_job.job_id,),
    )
    new_job = repository.claim_job("new-job-owner")
    assert new_job is not None
    check(old_job.lease_token != new_job.lease_token, "reclaim retained old token")
    record = repository.load_record(feedback_id)
    schema = load_decision_schema(ROOT / "schemas/feedback-decision/1.0.0/manifest.json")
    state = PrivacyBoundary().prepare_for_decision(record)
    envelope = build_decision_envelope(state, schema, RuleDecisionEngine().decide(state, schema))
    event = build_signal_projection_event(record, envelope)
    before = repository.counts()
    expect_lost_lease(lambda: repository.persist_success(old_job, envelope, event))
    check(repository.counts() == before, "stale job left decision/answer/outbox inserts")
    before_job = row(connection, "processing_jobs", new_job.job_id)
    repository.persist_failure(old_job, ValueError("stale failure"))
    check(
        row(connection, "processing_jobs", new_job.job_id) == before_job,
        "stale failure overwrote new job owner",
    )
    repository.persist_success(new_job, envelope, event)
    after = repository.counts()
    check(after["decisions"] == before["decisions"] + 1, "decision missing")
    check(after["answers"] == before["answers"] + len(envelope["answers"]), "answers missing")
    check(after["outbox"] == before["outbox"] + 1, "outbox missing")

    old_event = repository.claim_event("old-event-owner")
    assert old_event is not None
    connection.execute(
        "UPDATE feedback.outbox_events SET leased_until = clock_timestamp() - interval '1 second' "
        "WHERE event_id = %s",
        (old_event.event_id,),
    )
    new_event = repository.claim_event("new-event-owner")
    assert new_event is not None
    check(old_event.lease_token != new_event.lease_token, "event reclaim retained old token")
    before = repository.counts()
    expect_lost_lease(lambda: repository.persist_projection_success(old_event, "test"))
    check(repository.counts() == before, "stale projector left a ledger insert")
    before_event = row(connection, "outbox_events", new_event.event_id)
    repository.persist_projection_failure(old_event, ValueError("stale failure"))
    check(
        row(connection, "outbox_events", new_event.event_id) == before_event,
        "stale failure overwrote new event owner",
    )
    repository.persist_projection_success(new_event, "skipped.uncalibrated")
    check(repository.counts()["projections"] == before["projections"] + 1, "ledger missing")

    for table in ("decision_runs", "decision_answers"):
        for mutation in (
            f"UPDATE feedback.{table} SET decision_id = decision_id",
            f"DELETE FROM feedback.{table}",
        ):
            try:
                connection.execute(mutation)
            except psycopg.errors.ObjectNotInPrerequisiteState:
                pass
            else:
                raise AssertionError(f"immutable {table} allowed mutation")
    try:
        with connection.transaction():
            connection.execute("SET LOCAL ROLE feedback_projector")
            connection.execute("SELECT original_text FROM feedback.restricted_feedback_text")
    except psycopg.errors.InsufficientPrivilege:
        pass
    else:
        raise AssertionError("projector could read restricted text")
    print(
        "PASS: stale completion/failure fencing, atomic persistence, immutability, privacy grants",
        flush=True,
    )


def run_checks(dsn: str) -> None:
    with (
        psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as connection,
        StorageRepository(dsn) as repository,
    ):
        migrations = sorted((ROOT / "infra/postgres/migrations").glob("*.sql"))
        for path in migrations:
            if path.name < "004_lease_exhaustion.sql":
                repository.apply_migration(path)
        record = (
            SyntheticDatasetProvider(ROOT / "data/demo/feedback.jsonl").load_feedback().records[0]
        )
        schema = load_decision_schema(ROOT / "schemas/feedback-decision/1.0.0/manifest.json")
        repository.enqueue_record(record, schema, engine="rules", requested_model="rules-1.0.0")
        connection.execute("UPDATE feedback.processing_jobs SET status = 'dead'")
        job_id = seed(connection, "job", record.feedback_id, attempts=5, maximum=5, active=True)
        event_id = seed(connection, "event", record.feedback_id, attempts=8, maximum=8, active=True)
        check(repository.claim_job("before-upgrade") is None, "old claim unexpectedly succeeded")
        check(repository.claim_event("before-upgrade") is None, "old event claim succeeded")
        check(
            row(connection, "processing_jobs", job_id)["status"] == "running",
            "baseline final-attempt crash was not reproduced",
        )
        check(
            row(connection, "outbox_events", event_id)["status"] == "publishing",
            "baseline final-attempt event crash was not reproduced",
        )
        print("PASS: reproduced stranded final attempts before forward migration", flush=True)
        for path in migrations:
            if path.name >= "004_lease_exhaustion.sql":
                repository.apply_migration(path)
        check(repository.claim_job("after-upgrade") is None, "exhausted job was reclaimed")
        check(repository.claim_event("after-upgrade") is None, "exhausted event was reclaimed")
        for table, identity in (("processing_jobs", job_id), ("outbox_events", event_id)):
            result = row(connection, table, identity)
            check(
                result["status"] == "dead"
                and result["lease_token"] is None
                and result["lease_owner"] is None
                and result["leased_until"] is None,
                "expired exhausted owner was not terminalized and unfenced",
            )
        print("PASS: forward migration recovers expired exhausted jobs and events", flush=True)
        check_exhaustion(connection, repository, record.feedback_id)
        check_concurrent_claims(dsn, connection, record.feedback_id)
        check_transactions(connection, repository, record.feedback_id)


def main() -> None:
    name = f"feedback-quality-{uuid4().hex[:12]}"
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
            "127.0.0.1::5432",
            "--tmpfs",
            "/var/lib/postgresql",
            "--env",
            "POSTGRES_PASSWORD=disposable-quality-only",
            "postgres:18-alpine",
        )
        port = docker("port", container_id, "5432/tcp").rsplit(":", 1)[1]
        dsn = (
            f"host=127.0.0.1 port={port} dbname=postgres user=postgres "
            "password=disposable-quality-only connect_timeout=2"
        )
        deadline = time.monotonic() + 60
        while True:
            try:
                with psycopg.connect(dsn):
                    break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)
        run_checks(dsn)
    finally:
        if container_id:
            docker("rm", "--force", container_id)
            print(f"Removed disposable container {name}", flush=True)


if __name__ == "__main__":
    main()
