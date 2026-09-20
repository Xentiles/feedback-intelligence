"""Transactional PostgreSQL persistence for feedback jobs and decisions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from feedback_intelligence_worker.data.models import FeedbackRecord
from feedback_intelligence_worker.decision.schema import DecisionSchema

JOB_NAMESPACE = UUID("705aa244-e7a5-42e6-bc1f-da629fd24ec4")


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    job_id: str
    feedback_id: str
    lease_token: str
    attempt_count: int
    engine: str
    requested_model: str
    decision_schema_name: str
    decision_schema_version: str
    decision_schema_sha256: str
    traceparent: str | None
    tracestate: str | None


@dataclass(frozen=True, slots=True)
class ClaimedEvent:
    event_id: str
    lease_token: str
    attempt_count: int
    payload: dict[str, Any]
    traceparent: str | None = None
    tracestate: str | None = None


class StorageRepository:
    def __init__(self, dsn: str) -> None:
        self._connection: psycopg.Connection[dict[str, Any]] = psycopg.connect(
            dsn, row_factory=dict_row, autocommit=True
        )

    def __enter__(self) -> StorageRepository:
        return self

    def __exit__(self, *_: object) -> None:
        self._connection.close()

    def apply_migration(self, path: Path) -> bool:
        with self._connection.transaction():
            exists = self._connection.execute(
                "SELECT to_regclass('feedback.schema_migrations') AS table_name"
            ).fetchone()
            if exists is not None and exists["table_name"] is not None:
                applied = self._connection.execute(
                    "SELECT 1 FROM feedback.schema_migrations WHERE version = %s",
                    (path.stem,),
                ).fetchone()
                if applied is not None:
                    return False
        self._connection.execute(path.read_text(encoding="utf-8"), prepare=False)
        return True

    def enqueue_record(
        self,
        record: FeedbackRecord,
        schema: DecisionSchema,
        *,
        engine: str,
        requested_model: str,
    ) -> bool:
        canonical = record.to_dict()
        canonical_bytes = json.dumps(
            canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        checksum = hashlib.sha256(canonical_bytes).hexdigest()
        identity = f"{record.feedback_id}:{schema.sha256}:{engine}:{requested_model}"
        job_id = str(uuid5(JOB_NAMESPACE, identity))
        idempotency_key = f"sha256:{hashlib.sha256(identity.encode()).hexdigest()}"
        with self._connection.transaction():
            inserted = self._connection.execute(
                """
                INSERT INTO feedback.feedback_records (
                    feedback_id, schema_version, source_provider_id, source_dataset_name,
                    source_dataset_version, source_record_id, occurred_at, channel, language,
                    rating, related_products, order_id, metadata, operational_context,
                    canonical_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                ) ON CONFLICT (feedback_id) DO NOTHING
                RETURNING feedback_id
                """,
                (
                    record.feedback_id,
                    record.schema_version,
                    record.source.provider_id,
                    record.source.dataset_name,
                    record.source.dataset_version,
                    record.source.source_record_id,
                    record.occurred_at,
                    record.channel,
                    record.language,
                    Jsonb(None if record.rating is None else record.rating.to_dict()),
                    Jsonb([product.to_dict() for product in record.related_products]),
                    record.order_id,
                    Jsonb(record.metadata),
                    Jsonb(
                        None
                        if record.operational_context is None
                        else record.operational_context.to_dict()
                    ),
                    checksum,
                ),
            ).fetchone()
            if inserted is None:
                existing = self._connection.execute(
                    "SELECT canonical_sha256 FROM feedback.feedback_records WHERE feedback_id = %s",
                    (record.feedback_id,),
                ).fetchone()
                matches = existing is not None and existing["canonical_sha256"].strip() == checksum
                if not matches:
                    semantic = self._connection.execute(
                        "SELECT feedback.record_content_matches(%s, %s) AS matches",
                        (record.feedback_id, Jsonb(canonical)),
                    ).fetchone()
                    matches = semantic is not None and semantic["matches"] is True
                if not matches:
                    raise ValueError(f"Feedback identity collision for {record.feedback_id}")
            self._connection.execute(
                """
                INSERT INTO feedback.restricted_feedback_text (
                    feedback_id, original_text, title, privacy_status
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (feedback_id) DO NOTHING
                """,
                (record.feedback_id, record.original_text, record.title, record.privacy_status),
            )
            job = self._connection.execute(
                """
                INSERT INTO feedback.processing_jobs (
                    job_id, idempotency_key, feedback_id, decision_schema_name,
                    decision_schema_version, decision_schema_sha256, engine, requested_model
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING job_id
                """,
                (
                    job_id,
                    idempotency_key,
                    record.feedback_id,
                    schema.name,
                    schema.version,
                    schema.sha256,
                    engine,
                    requested_model,
                ),
            ).fetchone()
        return job is not None

    def claim_job(self, worker_name: str) -> ClaimedJob | None:
        with self._connection.transaction():
            row = self._connection.execute(
                "SELECT * FROM feedback.claim_processing_jobs(%s, 1, 60)",
                (worker_name,),
            ).fetchone()
        if row is None:
            return None
        return ClaimedJob(
            job_id=str(row["job_id"]),
            feedback_id=str(row["feedback_id"]),
            lease_token=str(row["lease_token"]),
            attempt_count=int(row["attempt_count"]),
            engine=str(row["engine"]),
            requested_model=str(row["requested_model"]),
            decision_schema_name=str(row["decision_schema_name"]),
            decision_schema_version=str(row["decision_schema_version"]),
            decision_schema_sha256=str(row["decision_schema_sha256"]),
            traceparent=None if row["traceparent"] is None else str(row["traceparent"]),
            tracestate=None if row["tracestate"] is None else str(row["tracestate"]),
        )

    def load_record(self, feedback_id: str) -> FeedbackRecord:
        row = self._connection.execute(
            """
            SELECT record.*, restricted.original_text, restricted.title,
                   restricted.privacy_status
            FROM feedback.feedback_records AS record
            JOIN feedback.restricted_feedback_text AS restricted USING (feedback_id)
            WHERE record.feedback_id = %s
            """,
            (feedback_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Feedback does not exist: {feedback_id}")
        return FeedbackRecord.from_dict(
            {
                "schema_version": row["schema_version"],
                "feedback_id": str(row["feedback_id"]),
                "source": {
                    "provider_id": row["source_provider_id"],
                    "dataset_name": row["source_dataset_name"],
                    "dataset_version": row["source_dataset_version"],
                    "source_record_id": row["source_record_id"],
                },
                "original_text": row["original_text"],
                "title": row["title"],
                "occurred_at": row["occurred_at"].isoformat(),
                "rating": row["rating"],
                "related_products": row["related_products"],
                "order_id": row["order_id"],
                "channel": row["channel"],
                "language": row["language"],
                "metadata": row["metadata"],
                "operational_context": row["operational_context"],
                "privacy_status": row["privacy_status"],
            }
        )

    def persist_success(
        self,
        job: ClaimedJob,
        envelope: dict[str, Any],
        event: dict[str, Any],
        *,
        traceparent: str | None = None,
        tracestate: str | None = None,
    ) -> None:
        schema = _object(envelope["schema"], "schema")
        engine = _object(envelope["engine"], "engine")
        input_metadata = _object(envelope["input"], "input")
        execution = _object(envelope["execution"], "execution")
        answers = _object(envelope["answers"], "answers")
        trace_id = event["trace_id"]
        with self._connection.transaction():
            self._connection.execute(
                """
                INSERT INTO feedback.decision_runs (
                    decision_id, job_id, feedback_id, decided_at, schema_name,
                    schema_version, schema_sha256, engine_provider, recorded_provider,
                    requested_model, resolved_model, policy_version,
                    redacted_text_sha256, language, channel, request_id, latency_ms,
                    input_tokens, output_tokens, trace_id
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) ON CONFLICT (decision_id) DO NOTHING
                """,
                (
                    envelope["decision_id"],
                    job.job_id,
                    envelope["feedback_id"],
                    envelope["decided_at"],
                    schema["name"],
                    schema["version"],
                    schema["sha256"],
                    engine["provider"],
                    engine["recorded_provider"],
                    engine["requested_model"],
                    engine["resolved_model"],
                    None,
                    input_metadata["redacted_text_sha256"],
                    input_metadata["language"],
                    input_metadata["channel"],
                    execution["request_id"],
                    execution["latency_ms"],
                    execution["input_tokens"],
                    execution["output_tokens"],
                    trace_id,
                ),
            )
            for question_id, answer_value in answers.items():
                answer = _object(answer_value, question_id)
                self._connection.execute(
                    """
                    INSERT INTO feedback.decision_answers (
                        decision_id, question_id, primitive, answer
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (decision_id, question_id) DO NOTHING
                    """,
                    (
                        envelope["decision_id"],
                        question_id,
                        answer["type"],
                        Jsonb(answer),
                    ),
                )
            self._connection.execute(
                """
                INSERT INTO feedback.outbox_events (
                    event_id, event_type, event_version, aggregate_id, payload,
                    traceparent, tracestate
                ) VALUES (%s, 'signal.projection.requested', %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (
                    event["event_id"],
                    event["event_version"],
                    envelope["decision_id"],
                    Jsonb(event),
                    traceparent,
                    tracestate,
                ),
            )
            updated = self._connection.execute(
                """
                UPDATE feedback.processing_jobs
                SET status = 'succeeded', completed_at = clock_timestamp(),
                    leased_until = NULL, lease_owner = NULL, lease_token = NULL,
                    updated_at = clock_timestamp()
                WHERE job_id = %s AND status = 'running' AND lease_token = %s
                RETURNING job_id
                """,
                (job.job_id, job.lease_token),
            ).fetchone()
            if updated is None:
                raise ValueError(f"Job lease was lost before persistence: {job.job_id}")

    def persist_failure(self, job: ClaimedJob, error: Exception) -> None:
        with self._connection.transaction():
            self._connection.execute(
                """
                UPDATE feedback.processing_jobs
                SET status = CASE WHEN attempt_count >= max_attempts
                                  THEN 'dead' ELSE 'retry_wait' END,
                    available_at = clock_timestamp() + (%s * interval '1 second'),
                    leased_until = NULL, lease_owner = NULL, lease_token = NULL,
                    last_error_code = %s, last_error_message = %s,
                    updated_at = clock_timestamp()
                WHERE job_id = %s AND status = 'running' AND lease_token = %s
                """,
                (
                    min(2**job.attempt_count, 300),
                    type(error).__name__,
                    "Decision processing failed; inspect the error code and job attempt metadata",
                    job.job_id,
                    job.lease_token,
                ),
            )

    def claim_event(self, worker_name: str) -> ClaimedEvent | None:
        with self._connection.transaction():
            row = self._connection.execute(
                "SELECT * FROM feedback.claim_outbox_events(%s, 1, 60)",
                (worker_name,),
            ).fetchone()
        if row is None:
            return None
        return ClaimedEvent(
            event_id=str(row["event_id"]),
            lease_token=str(row["lease_token"]),
            attempt_count=int(row["attempt_count"]),
            payload=_object(row["payload"], "payload"),
            traceparent=None if row["traceparent"] is None else str(row["traceparent"]),
            tracestate=None if row["tracestate"] is None else str(row["tracestate"]),
        )

    def persist_projection_success(self, event: ClaimedEvent, destination: str) -> None:
        with self._connection.transaction():
            self._connection.execute(
                """
                INSERT INTO feedback.projection_ledger (
                    event_id, projection_id, destination
                ) VALUES (%s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (event.event_id, event.payload["projection_id"], destination),
            )
            updated = self._connection.execute(
                """
                UPDATE feedback.outbox_events
                SET status = 'published', published_at = clock_timestamp(),
                    leased_until = NULL, lease_owner = NULL, lease_token = NULL,
                    updated_at = clock_timestamp()
                WHERE event_id = %s AND status = 'publishing' AND lease_token = %s
                RETURNING event_id
                """,
                (event.event_id, event.lease_token),
            ).fetchone()
            if updated is None:
                raise ValueError(f"Outbox lease was lost before persistence: {event.event_id}")

    def persist_projection_failure(self, event: ClaimedEvent, error: Exception) -> None:
        with self._connection.transaction():
            self._connection.execute(
                """
                UPDATE feedback.outbox_events
                SET status = CASE WHEN attempt_count >= max_attempts
                                  THEN 'dead' ELSE 'retry_wait' END,
                    available_at = clock_timestamp() + (%s * interval '1 second'),
                    leased_until = NULL, lease_owner = NULL, lease_token = NULL,
                    last_error_code = %s, last_error_message = %s,
                    updated_at = clock_timestamp()
                WHERE event_id = %s AND status = 'publishing' AND lease_token = %s
                """,
                (
                    min(2**event.attempt_count, 300),
                    type(error).__name__,
                    "Projection failed; inspect the error code and event attempt metadata",
                    event.event_id,
                    event.lease_token,
                ),
            )

    def counts(self) -> dict[str, int]:
        row = self._connection.execute(
            """
            SELECT
                (SELECT count(*) FROM feedback.feedback_records) AS feedback,
                (SELECT count(*) FROM feedback.processing_jobs) AS jobs,
                (SELECT count(*) FROM feedback.decision_runs) AS decisions,
                (SELECT count(*) FROM feedback.decision_answers) AS answers,
                (SELECT count(*) FROM feedback.outbox_events) AS outbox,
                (SELECT count(*) FROM feedback.projection_ledger) AS projections
            """
        ).fetchone()
        if row is None:
            raise ValueError("Could not read storage counts")
        return {key: int(value) for key, value in row.items()}


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value
