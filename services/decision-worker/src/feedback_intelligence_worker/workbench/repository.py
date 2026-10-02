"""Dataset-scoped PostgreSQL orchestration with leases and immutable results."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from feedback_intelligence_worker.privacy.models import is_model_language
from feedback_intelligence_worker.workbench.analysis import (
    PROTOCOL_HASH,
    builtin_templates,
    sample_records,
    validate_template,
)


class Repository:
    def __init__(self, dsn: str) -> None:
        self.db = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)

    def __enter__(self) -> Repository:
        return self

    def __exit__(self, *_: object) -> None:
        self.db.close()

    def one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
        row = self.db.execute(sql, params).fetchone()
        if row is None:
            raise LookupError("Resource does not exist")
        return row

    def dataset(self, identity: str) -> dict[str, Any]:
        UUID(identity)
        return self.one(
            "SELECT * FROM workbench.datasets WHERE id=%s AND status='ready'", (identity,)
        )

    def templates(self) -> list[dict[str, Any]]:
        for template in builtin_templates():
            self.save_template(template)
        return list(
            self.db.execute(
                "SELECT id,name,revision,payload FROM workbench.templates ORDER BY created_at,id"
            )
        )

    def save_template(self, template: dict[str, Any]) -> dict[str, Any]:
        value = validate_template(template)
        self.db.execute(
            (
                "INSERT INTO workbench.templates(id,name,revision,payload) VALUES(%s,%s,%s,%s) "
                "ON CONFLICT(revision) DO NOTHING"
            ),
            (uuid4(), value["name"], value["revision"], Jsonb(value)),
        )
        return self.one(
            "SELECT id,name,revision,payload FROM workbench.templates WHERE revision=%s",
            (value["revision"],),
        )

    def import_dataset(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise ValueError("Dataset name must be 1-100 characters")
        if not data["records"]:
            raise ValueError("No valid records to import")
        identity = uuid4()
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO workbench.datasets(id,name,snapshot,validation) VALUES(%s,%s,%s,%s)",
                (
                    identity,
                    name.strip(),
                    data["snapshot"],
                    Jsonb({"summary": data["summary"], "issues": data["issues"]}),
                ),
            )
            with self.db.cursor() as cursor:
                cursor.executemany(
                    (
                        "INSERT INTO "
                        "workbench.records(dataset_id,id,position,source_id,orig"
                        "inal_text,occurred_at,language,channel,rating,groups) V"
                        "ALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                    ),
                    [
                        (
                            identity,
                            r["id"],
                            r["position"],
                            r["sourceId"],
                            r["text"],
                            r["occurredAt"],
                            r["language"],
                            r["channel"],
                            Jsonb(r["rating"]),
                            Jsonb(r["groups"]),
                        )
                        for r in data["records"]
                    ],
                )
        return self.dataset(str(identity))

    def records(self, dataset_id: str) -> list[dict[str, Any]]:
        self.dataset(dataset_id)
        return [
            self.record(row)
            for row in self.db.execute(
                "SELECT * FROM workbench.records WHERE dataset_id=%s ORDER BY position",
                (dataset_id,),
            )
        ]

    @staticmethod
    def record(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "schemaVersion": "workbench-record/1.0.0",
            "id": str(row["id"]),
            "position": row["position"],
            "sourceId": row["source_id"],
            "text": row["original_text"],
            "occurredAt": None if row["occurred_at"] is None else row["occurred_at"].isoformat(),
            "language": row["language"]
            if row["language"] and is_model_language(row["language"])
            else None,
            "channel": row["channel"],
            "rating": row["rating"],
            "groups": row["groups"],
        }

    def create_run(self, options: dict[str, Any]) -> dict[str, Any]:
        dataset_id = str(options["datasetId"])
        dataset = self.dataset(dataset_id)
        template = self.one(
            "SELECT * FROM workbench.templates WHERE id=%s", (UUID(options["templateId"]),)
        )
        engine = options.get("engine", "rules")
        if engine not in ("rules", "openai"):
            raise ValueError("Choose rules or OpenAI")
        mode = options.get("mode", "sample" if engine == "openai" else "full")
        if mode not in ("sample", "full"):
            raise ValueError("Choose sample or full")
        if engine == "openai" and (
            options.get("externalConsent") is not True
            or not options.get("connectionId")
            or not options.get("model")
        ):
            raise ValueError(
                "AI requires an explicit connection, model and external-processing consent"
            )
        key = str(UUID(options["idempotencyKey"]))
        snapshot = {
            "datasetSnapshot": dataset["snapshot"],
            "template": template["payload"],
            "templateRevision": template["revision"],
            "engine": engine,
            "model": options.get("model") if engine == "openai" else "keywords-1.0.0",
            "connectionId": options.get("connectionId") if engine == "openai" else None,
            "mode": mode,
            "protocolHash": PROTOCOL_HASH,
            "privacyVersion": "deterministic-redactor/1.0.0",
            "sampleRunId": options.get("sampleRunId"),
            "billingMode": options.get("billingMode") if engine == "openai" else "none",
        }
        records = self.records(dataset_id)
        selected = sample_records(records) if mode == "sample" else records
        identity = uuid4()
        with self.db.transaction():
            self.one(
                "SELECT * FROM workbench.datasets WHERE id=%s AND status='ready' FOR UPDATE",
                (dataset_id,),
            )
            existing = self.db.execute(
                "SELECT * FROM workbench.runs WHERE idempotency_key=%s", (key,)
            ).fetchone()
            if existing:
                if existing["snapshot"] != snapshot or str(existing["dataset_id"]) != dataset_id:
                    raise ValueError("Idempotency key already belongs to another run request")
                return existing
            self.db.execute(
                (
                    "INSERT INTO "
                    "workbench.runs(id,dataset_id,template_id,snapshot,idempotency_key) "
                    "VALUES(%s,%s,%s,%s,%s)"
                ),
                (identity, dataset_id, template["id"], Jsonb(snapshot), key),
            )
            with self.db.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO workbench.jobs(run_id,record_id) VALUES(%s,%s)",
                    [(identity, r["id"]) for r in selected],
                )
            if mode == "full" and snapshot["sampleRunId"]:
                previous = self.run(str(snapshot["sampleRunId"]))
                if previous["status"] != "completed" or previous["succeeded"] == 0:
                    raise ValueError("Complete a successful sample before expanding the run")
                for field in (
                    "datasetSnapshot",
                    "templateRevision",
                    "engine",
                    "model",
                    "connectionId",
                    "protocolHash",
                    "privacyVersion",
                    "billingMode",
                ):
                    if (
                        previous["snapshot"][field] != snapshot[field]
                        or str(previous["dataset_id"]) != dataset_id
                    ):
                        raise ValueError("Sample and full run configurations must match")
                results = self.db.execute(
                    "SELECT * FROM workbench.results WHERE run_id=%s", (previous["id"],)
                ).fetchall()
                for result in results:
                    self.db.execute(
                        (
                            "UPDATE workbench.jobs SET status='succeeded' WHERE run_"
                            "id=%s AND record_id=%s"
                        ),
                        (identity, result["record_id"]),
                    )
                    self.store_result(
                        str(identity),
                        str(result["record_id"]),
                        dataset_id,
                        {**result["payload"], "reusedFromRun": str(previous["id"])},
                    )
        return self.run(str(identity))

    def run(self, identity: str) -> dict[str, Any]:
        UUID(identity)
        result = self.one(
            (
                "SELECT r.*, (SELECT count(*) FROM workbench.jobs j WHERE j.run_id=r.id) AS "
                "target, (SELECT count(*) FROM workbench.jobs j WHERE j.run_id=r.id AND "
                "j.status='succeeded') AS succeeded, (SELECT count(*) FROM workbench.jobs j "
                "WHERE j.run_id=r.id AND j.status='failed') AS failed FROM workbench.runs r "
                "JOIN workbench.datasets d ON d.id=r.dataset_id WHERE r.id=%s AND "
                "d.status='ready'"
            ),
            (identity,),
        )
        result["errors"] = list(
            self.db.execute(
                "SELECT record_id,status,error_code FROM workbench.jobs WHERE run_id=%s "
                "AND error_code IS NOT NULL ORDER BY record_id LIMIT 100",
                (identity,),
            )
        )
        result["elapsedSeconds"] = max(
            0,
            int(
                (
                    (result["completed_at"] or datetime.now(UTC)) - result["created_at"]
                ).total_seconds()
            ),
        )
        return result

    def change_run(self, identity: str, action: str) -> dict[str, Any]:
        with self.db.transaction():
            run = self.one("SELECT * FROM workbench.runs WHERE id=%s FOR UPDATE", (UUID(identity),))
            self.dataset(str(run["dataset_id"]))
            if action == "cancel":
                self.db.execute(
                    (
                        "UPDATE workbench.runs SET status='cancelled' WHERE id=%s AND status IN "
                        "('running','queued','paused')"
                    ),
                    (identity,),
                )
            elif action == "resume":
                if run["status"] not in ("cancelled", "paused", "failed"):
                    raise ValueError("Only stopped runs can resume")
                self.db.execute(
                    (
                        "UPDATE workbench.jobs SET status='pending',lease_token="
                        "NULL,leased_until=NULL "
                        "WHERE run_id=%s AND status IN ('running','failed','interrupted')"
                    ),
                    (identity,),
                )
                self.db.execute(
                    "UPDATE workbench.runs SET status='queued',completed_at=NULL WHERE id=%s",
                    (identity,),
                )
            else:
                raise ValueError("Unknown run action")
        return self.run(identity)

    def result_snapshot(self, identity: str) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
        """Read run counters, immutable decisions and projection state together."""
        with self.db.transaction():
            self.db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            run = self.run(identity)
            rows = self.result_rows(identity, run)
            pending = int(
                self.one(
                    "SELECT count(*) AS n FROM workbench.outbox WHERE run_id=%s AND "
                    "status<>'published'",
                    (identity,),
                )["n"]
            )
        return run, rows, pending

    def result_rows(self, identity: str, run: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        selected_run = self.run(identity) if run is None else run
        self.dataset(str(selected_run["dataset_id"]))
        return [
            {**self.record(row), "result": row["classification_payload"]}
            for row in self.db.execute(
                (
                    "SELECT r.*, s.payload AS classification_payload FROM workbench.results s "
                    "JOIN workbench.records r ON r.dataset_id=%s AND r.id=s.record_id "
                    "WHERE s.run_id=%s ORDER BY r.position,r.id"
                ),
                (selected_run["dataset_id"], identity),
            )
        ]

    def claim(self, run_id: str | None = None) -> dict[str, Any] | None:
        with self.db.transaction():
            # Lock the run before its job; cancellation and result commits use the same order.
            run = self.db.execute(
                "SELECT r.* FROM workbench.runs r JOIN workbench.datasets d ON "
                "d.id=r.dataset_id WHERE r.status IN ('queued','running') AND d.status='ready' "
                "AND (%s::uuid IS NULL OR r.id=%s::uuid) "
                "ORDER BY r.created_at FOR UPDATE OF r SKIP LOCKED LIMIT 1",
                (run_id, run_id),
            ).fetchone()
            if not run:
                return None
            self.db.execute(
                (
                    "UPDATE workbench.jobs SET "
                    "status='interrupted',error_code='lease_expired',lease_token=NULL WHERE "
                    "run_id=%s AND status='running' AND leased_until<now()"
                ),
                (run["id"],),
            )
            interrupted = self.db.execute(
                "SELECT 1 FROM workbench.jobs WHERE run_id=%s AND status='interrupted' LIMIT 1",
                (run["id"],),
            ).fetchone()
            if interrupted:
                self.db.execute(
                    "UPDATE workbench.runs SET status='paused' WHERE id=%s", (run["id"],)
                )
                return None
            self.db.execute(
                "UPDATE workbench.jobs SET status='failed',error_code='attempt_limit' "
                "WHERE run_id=%s AND status='pending' AND attempt>=3",
                (run["id"],),
            )
            job = self.db.execute(
                (
                    "SELECT * FROM workbench.jobs WHERE run_id=%s AND status='pending' ORDER BY "
                    "record_id FOR UPDATE SKIP LOCKED LIMIT 1"
                ),
                (run["id"],),
            ).fetchone()
            if not job:
                active = self.db.execute(
                    "SELECT 1 FROM workbench.jobs WHERE run_id=%s AND status='running' LIMIT 1",
                    (run["id"],),
                ).fetchone()
                if not active:
                    self.db.execute(
                        (
                            "UPDATE workbench.runs SET status='completed',completed_"
                            "at=now() WHERE id=%s"
                        ),
                        (run["id"],),
                    )
                return None
            token = uuid4()
            self.db.execute(
                (
                    "UPDATE workbench.jobs SET "
                    "status='running',attempt=attempt+1,lease_token=%s,leased_until=now()+interval "
                    "'180 seconds' WHERE run_id=%s AND record_id=%s"
                ),
                (token, run["id"], job["record_id"]),
            )
            self.db.execute("UPDATE workbench.runs SET status='running' WHERE id=%s", (run["id"],))
            record = self.one(
                "SELECT * FROM workbench.records WHERE dataset_id=%s AND id=%s",
                (run["dataset_id"], job["record_id"]),
            )
            return {**run, "record": self.record(record), "lease": str(token)}

    def store_result(
        self, run_id: str, record_id: str, dataset_id: str, result: dict[str, Any]
    ) -> None:
        self.db.execute(
            "INSERT INTO workbench.results(run_id,record_id,payload) VALUES(%s,%s,%s)",
            (run_id, record_id, Jsonb(result)),
        )
        row = self.one(
            "SELECT occurred_at,language FROM workbench.records WHERE dataset_id=%s AND id=%s",
            (dataset_id, record_id),
        )
        event = {
            "projection_id": str(uuid4()),
            "dataset_id": dataset_id,
            "run_id": run_id,
            "record_id": record_id,
            "occurred_at": None if row["occurred_at"] is None else row["occurred_at"].isoformat(),
            "language": row["language"]
            if row["language"] and is_model_language(row["language"])
            else None,
            "topic": result["topic"],
            "sentiment": result["sentiment"],
            "actionable": int(result["actionable"]),
            "template_revision": result["templateRevision"],
        }
        self.db.execute(
            (
                "INSERT INTO workbench.outbox(id,dataset_id,run_id,record_id,payload) "
                "VALUES(%s,%s,%s,%s,%s)"
            ),
            (event["projection_id"], dataset_id, run_id, record_id, Jsonb(event)),
        )

    def finish(
        self,
        job: dict[str, Any],
        result: dict[str, Any] | None,
        error_code: str | None = None,
        pause: bool = False,
    ) -> bool:
        with self.db.transaction():
            run = self.one("SELECT * FROM workbench.runs WHERE id=%s FOR UPDATE", (job["id"],))
            current = self.one(
                "SELECT * FROM workbench.jobs WHERE run_id=%s AND record_id=%s FOR UPDATE",
                (job["id"], job["record"]["id"]),
            )
            if str(current["lease_token"]) != job["lease"] or run["status"] not in (
                "running",
                "queued",
            ):
                return False
            if current["leased_until"] <= self.one("SELECT now() AS time")["time"]:
                return False
            if result is not None:
                self.store_result(
                    str(job["id"]), job["record"]["id"], str(job["dataset_id"]), result
                )
            self.db.execute(
                (
                    "UPDATE workbench.jobs SET "
                    "status=%s,error_code=%s,lease_token=NULL,leased_until=NULL WHERE run_id=%s "
                    "AND record_id=%s"
                ),
                (
                    "succeeded" if result is not None else "interrupted" if pause else "failed",
                    error_code,
                    job["id"],
                    job["record"]["id"],
                ),
            )
            if pause:
                self.db.execute(
                    "UPDATE workbench.runs SET status='paused' WHERE id=%s", (job["id"],)
                )
            return True

    def mark_delete(self, identity: str) -> None:
        with self.db.transaction():
            self.one(
                "SELECT id FROM workbench.datasets WHERE id=%s AND status='ready' FOR UPDATE",
                (UUID(identity),),
            )
            self.db.execute(
                "UPDATE workbench.datasets SET status='deleting' WHERE id=%s", (identity,)
            )
            self.db.execute(
                "UPDATE workbench.runs SET status='cancelled' WHERE dataset_id=%s", (identity,)
            )

    def purge(self, identity: str) -> None:
        with self.db.transaction():
            dataset = self.one(
                "SELECT * FROM workbench.datasets WHERE id=%s FOR UPDATE", (identity,)
            )
            if dataset["status"] != "deleting":
                raise ValueError("Dataset is not pending purge")
            # Worker drain and projector run on one loop. API cancellation fences active commits.
            for table in ("results", "jobs"):
                self.db.execute(
                    f"DELETE FROM workbench.{table} WHERE run_id IN "
                    "(SELECT id FROM workbench.runs WHERE dataset_id=%s)",
                    (identity,),
                )
            self.db.execute("DELETE FROM workbench.outbox WHERE dataset_id=%s", (identity,))
            self.db.execute("DELETE FROM workbench.runs WHERE dataset_id=%s", (identity,))
            self.db.execute("DELETE FROM workbench.records WHERE dataset_id=%s", (identity,))
            self.db.execute(
                (
                    "UPDATE workbench.datasets SET status='deleted',name='Deleted "
                    "dataset',snapshot='',validation='{}'::jsonb WHERE id=%s"
                ),
                (identity,),
            )
