"""Run the idempotent PostgreSQL decision and ClickHouse projection pipeline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import psycopg

from feedback_intelligence_worker.data.config import find_repository_root
from feedback_intelligence_worker.data.providers.synthetic import SyntheticDatasetProvider
from feedback_intelligence_worker.decision.envelope import build_decision_envelope
from feedback_intelligence_worker.decision.fixture import FixtureDecisionEngine
from feedback_intelligence_worker.decision.schema import load_decision_schema
from feedback_intelligence_worker.privacy import PrivacyBoundary
from feedback_intelligence_worker.storage.clickhouse import ClickHouseClient
from feedback_intelligence_worker.storage.events import build_signal_projection_event
from feedback_intelligence_worker.storage.repository import StorageRepository


def build_parser() -> argparse.ArgumentParser:
    root = find_repository_root()
    parser = argparse.ArgumentParser(prog="feedback-storage")
    parser.add_argument("command", choices=("demo", "migrate"))
    parser.add_argument("--postgres-dsn", default=os.getenv("POSTGRES_DSN"))
    parser.add_argument("--clickhouse-url", default=os.getenv("CLICKHOUSE_URL"))
    parser.add_argument("--clickhouse-user", default=os.getenv("CLICKHOUSE_USER"))
    parser.add_argument("--clickhouse-password", default=os.getenv("CLICKHOUSE_PASSWORD"))
    parser.add_argument(
        "--postgres-migrations",
        type=Path,
        default=root / "infra/postgres/migrations",
    )
    parser.add_argument(
        "--clickhouse-migration",
        type=Path,
        default=root / "infra/clickhouse/migrations/001_analytics_model.sql",
    )
    parser.add_argument(
        "--clickhouse-trend-migration",
        type=Path,
        default=root / "infra/clickhouse/migrations/002_trend_inputs.sql",
    )
    parser.add_argument("--source", type=Path, default=root / "data/demo/feedback.jsonl")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=root / "data/fixtures/decisions/demo-semif-qwen3.5-4b-mlx-q4.json",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=root / "schemas/feedback-decision/1.0.0/manifest.json",
    )
    parser.add_argument("--model", default="semif-qwen3.5-4b-mlx-q4-851bf6e8")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if not arguments.postgres_dsn:
            raise ValueError("POSTGRES_DSN or --postgres-dsn is required")
        clickhouse = _clickhouse(arguments)
        with StorageRepository(arguments.postgres_dsn) as repository:
            postgres_migration_paths = sorted(arguments.postgres_migrations.glob("*.sql"))
            if not postgres_migration_paths:
                raise ValueError("No PostgreSQL migrations were found")
            applied_postgres_migrations = [
                path.name for path in postgres_migration_paths if repository.apply_migration(path)
            ]
            clickhouse.apply_migration(arguments.clickhouse_migration)
            clickhouse.apply_migration(arguments.clickhouse_trend_migration)
            if arguments.command == "migrate":
                payload: dict[str, object] = {
                    "postgres_migrated": bool(applied_postgres_migrations),
                    "postgres_migrations": applied_postgres_migrations,
                    "clickhouse_migrated": True,
                }
            else:
                payload = _run_demo(arguments, repository, clickhouse)
        if arguments.as_json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(json.dumps(payload, sort_keys=True))
        return 0
    except (OSError, ValueError, psycopg.Error, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _run_demo(
    arguments: argparse.Namespace,
    repository: StorageRepository,
    clickhouse: ClickHouseClient,
) -> dict[str, object]:
    schema = load_decision_schema(arguments.schema)
    source = SyntheticDatasetProvider(arguments.source).load_feedback()
    if not source.validation.is_usable:
        raise ValueError("Demo source has blocking validation errors")
    enqueued = sum(
        repository.enqueue_record(
            record,
            schema,
            engine="fixture",
            requested_model=arguments.model,
        )
        for record in source.records
    )
    engine = FixtureDecisionEngine(arguments.fixture)
    boundary = PrivacyBoundary()
    processed = 0
    while (job := repository.claim_job("demo-decision-worker")) is not None:
        try:
            record = repository.load_record(job.feedback_id)
            state = boundary.prepare_for_decision(record)
            result = engine.decide(state, schema)
            envelope = build_decision_envelope(state, schema, result)
            event = build_signal_projection_event(record, envelope)
            repository.persist_success(job, envelope, event)
            processed += 1
        except Exception as error:
            repository.persist_failure(job, error)
            raise

    projected = 0
    skipped_uncalibrated = 0
    while (claimed_event := repository.claim_event("demo-clickhouse-projector")) is not None:
        try:
            eligibility = claimed_event.payload.get("eligibility")
            if not isinstance(eligibility, dict):
                raise ValueError("Projection event eligibility must be an object")
            if any(value is True for value in eligibility.values()):
                clickhouse.insert_event(claimed_event.payload)
                destination = "clickhouse.signal_facts"
                projected += 1
            else:
                destination = "skipped.uncalibrated"
                skipped_uncalibrated += 1
            repository.persist_projection_success(claimed_event, destination)
        except Exception as error:
            repository.persist_projection_failure(claimed_event, error)
            raise

    return {
        "enqueued": enqueued,
        "processed": processed,
        "projected": projected,
        "skipped_uncalibrated": skipped_uncalibrated,
        "postgres": repository.counts(),
        "clickhouse": {
            "signal_facts": clickhouse.scalar(
                "SELECT count() FROM feedback_intelligence.signal_facts FINAL"
            ),
            "aggregate_rows": clickhouse.scalar(
                "SELECT count() FROM feedback_intelligence.daily_signal_rollup"
            ),
        },
        "policy_status": "uncalibrated",
        "aggregate_eligible_decisions": 0,
    }


def _clickhouse(arguments: argparse.Namespace) -> ClickHouseClient:
    if not arguments.clickhouse_url:
        raise ValueError("CLICKHOUSE_URL or --clickhouse-url is required")
    if not arguments.clickhouse_user:
        raise ValueError("CLICKHOUSE_USER or --clickhouse-user is required")
    if not arguments.clickhouse_password:
        raise ValueError("CLICKHOUSE_PASSWORD or --clickhouse-password is required")
    return ClickHouseClient(
        arguments.clickhouse_url,
        arguments.clickhouse_user,
        arguments.clickhouse_password,
    )


if __name__ == "__main__":
    raise SystemExit(main())
