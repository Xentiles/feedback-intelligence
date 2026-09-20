"""Bidirectional Python/API ingestion against a fresh disposable PostgreSQL only.

Requires installed postgres:18-alpine and mcr.microsoft.com/dotnet/sdk:10.0.401
images and restored API packages. No application .env or existing database is used.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg
from feedback_intelligence_worker.data.providers.synthetic import SyntheticDatasetProvider
from feedback_intelligence_worker.decision.schema import load_decision_schema
from feedback_intelligence_worker.storage.repository import StorageRepository
from psycopg.types.json import Jsonb
from quality_storage_check import ROOT, check, docker


def main() -> None:
    container = ""
    try:
        container = docker(
            "run",
            "--detach",
            "--rm",
            "--pull=never",
            "--name",
            f"feedback-ingestion-quality-{uuid4().hex[:12]}",
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
        port = docker("port", container, "5432/tcp").rsplit(":", 1)[1]
        dsn = (
            f"host=127.0.0.1 port={port} dbname=postgres user=postgres "
            "password=disposable-quality-only"
        )
        deadline = time.monotonic() + 60
        while True:
            try:
                with psycopg.connect(dsn, connect_timeout=2):
                    break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)
        records = (
            SyntheticDatasetProvider(ROOT / "data/demo/feedback.jsonl").load_feedback().records
        )
        schema = load_decision_schema(ROOT / "schemas/feedback-decision/1.0.0/manifest.json")
        with StorageRepository(dsn) as repository:
            for migration in sorted((ROOT / "infra/postgres/migrations").glob("*.sql")):
                repository.apply_migration(migration)
            check(
                repository.enqueue_record(
                    records[0], schema, engine="rules", requested_model="rules-1.0.0"
                ),
                "Python seed not created",
            )
        cache = Path("/tmp/feedback-intelligence-nuget-cache")
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--pull=never",
                "--network",
                f"container:{container}",
                "-v",
                f"{ROOT}:/work",
                "-v",
                f"{cache}:/root/.nuget/packages",
                "-w",
                "/work",
                "-e",
                "QUALITY_POSTGRES_DSN=Host=127.0.0.1;Database=postgres;Username=postgres;Password=disposable-quality-only",
                "mcr.microsoft.com/dotnet/sdk:10.0.401",
                "dotnet",
                "test",
                "services/api/FeedbackIntelligence.sln",
                "--configuration",
                "Release",
                "--no-restore",
                "--filter",
                "FullyQualifiedName~PostgresIngestionTests",
            ],
            check=True,
        )
        with StorageRepository(dsn) as repository:
            second = replace(records[1], metadata={"a": "å", "z": 1})
            check(
                not repository.enqueue_record(
                    second, schema, engine="rules", requested_model="rules-1.0.0"
                ),
                "API→Python duplicate created work",
            )
            try:
                repository.enqueue_record(
                    replace(second, original_text="Changed content"),
                    schema,
                    engine="rules",
                    requested_model="rules-1.0.0",
                )
            except ValueError:
                pass
            else:
                raise AssertionError("Changed feedback content was silently accepted")
            check(repository.counts()["jobs"] == 2, "Duplicate/conflict added work")
        with psycopg.connect(dsn, autocommit=True) as connection:
            canonical = records[0].to_dict()
            canonical["occurred_at"] = str(canonical["occurred_at"]).replace("Z", "+00:00")
            matches = connection.execute(
                "SELECT feedback.record_content_matches(%s, %s)",
                (records[0].feedback_id, Jsonb(canonical)),
            ).fetchone()
            check(matches == (True,), "Equivalent UTC instant was rejected")
            try:
                with connection.transaction():
                    connection.execute("SET LOCAL ROLE feedback_projector")
                    connection.execute(
                        "SELECT feedback.record_content_matches(%s, %s)",
                        (records[0].feedback_id, Jsonb(canonical)),
                    )
            except psycopg.errors.InsufficientPrivilege:
                pass
            else:
                raise AssertionError("Projector gained access to restricted content comparison")
        print(
            "PASS: Python→API and API→Python duplicates, JSON numeric/key-order equivalence, "
            "UTC equivalence, changed-content conflicts, projector denial; two jobs"
        )
    finally:
        if container:
            docker("rm", "--force", container)
            print("Removed isolated ingestion PostgreSQL container")


if __name__ == "__main__":
    main()
