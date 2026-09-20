"""Continuous worker orchestration tests over in-memory lease doubles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from feedback_intelligence_worker.data.models import FeedbackRecord
from feedback_intelligence_worker.data.providers.synthetic import SyntheticDatasetProvider
from feedback_intelligence_worker.decision.rules import RULE_MODEL
from feedback_intelligence_worker.decision.schema import load_decision_schema
from feedback_intelligence_worker.service import build_engine_factory, drain_once
from feedback_intelligence_worker.storage.repository import ClaimedEvent, ClaimedJob


def test_drain_once_processes_job_and_closes_uncalibrated_outbox() -> None:
    root = Path(__file__).resolve().parents[3]
    record = SyntheticDatasetProvider(root / "data/demo/feedback.jsonl").load_feedback().records[0]
    repository = FakeRepository(record, engine="rules", requested_model=RULE_MODEL)
    projector = FakeProjector()
    schema = load_decision_schema(root / "schemas/feedback-decision/1.0.0/manifest.json")

    result = drain_once(
        repository,
        projector,
        schema,
        build_engine_factory(root / "data/fixtures/decisions/demo-semif-qwen3.5-4b-mlx-q4.json"),
        "test-worker",
    )

    assert result.jobs_claimed == 1
    assert result.jobs_succeeded == 1
    assert result.events_claimed == 1
    assert result.events_skipped == 1
    assert result.events_projected == 0
    assert repository.job_failure is None
    assert repository.projection_destination == "skipped.uncalibrated"
    assert projector.events == []
    assert repository.envelope is not None
    serialized = str(repository.envelope)
    assert record.original_text not in serialized


def test_drain_once_persists_retryable_job_failure_and_keeps_running() -> None:
    root = Path(__file__).resolve().parents[3]
    record = SyntheticDatasetProvider(root / "data/demo/feedback.jsonl").load_feedback().records[0]
    repository = FakeRepository(record, engine="unsupported", requested_model="none")
    projector = FakeProjector()
    schema = load_decision_schema(root / "schemas/feedback-decision/1.0.0/manifest.json")

    result = drain_once(
        repository,
        projector,
        schema,
        build_engine_factory(root / "data/fixtures/decisions/demo-semif-qwen3.5-4b-mlx-q4.json"),
        "test-worker",
    )

    assert result.jobs_claimed == 1
    assert result.jobs_failed == 1
    assert result.events_claimed == 0
    assert isinstance(repository.job_failure, ValueError)
    assert repository.envelope is None


def test_drain_once_rejects_job_for_a_different_schema_before_loading_text() -> None:
    root = Path(__file__).resolve().parents[3]
    record = SyntheticDatasetProvider(root / "data/demo/feedback.jsonl").load_feedback().records[0]
    repository = FakeRepository(
        record,
        engine="rules",
        requested_model=RULE_MODEL,
        schema_sha256="sha256:" + ("0" * 64),
    )
    schema = load_decision_schema(root / "schemas/feedback-decision/1.0.0/manifest.json")

    result = drain_once(
        repository,
        FakeProjector(),
        schema,
        build_engine_factory(root / "data/fixtures/decisions/demo-semif-qwen3.5-4b-mlx-q4.json"),
        "test-worker",
    )

    assert result.jobs_failed == 1
    assert isinstance(repository.job_failure, ValueError)
    assert repository.loaded_records == 0


class FakeRepository:
    def __init__(
        self,
        record: FeedbackRecord,
        *,
        engine: str,
        requested_model: str,
        schema_sha256: str = (
            "sha256:9314b38daf329f4c61fbea3d64f9a76a8d6334511888dcd61f7c75563c8f7094"
        ),
    ) -> None:
        self.record = record
        self.job: ClaimedJob | None = ClaimedJob(
            job_id="00000000-0000-0000-0000-000000000010",
            feedback_id=record.feedback_id,
            lease_token="00000000-0000-0000-0000-000000000011",
            attempt_count=1,
            engine=engine,
            requested_model=requested_model,
            decision_schema_name="feedback-decision",
            decision_schema_version="1.0.0",
            decision_schema_sha256=schema_sha256,
            traceparent=None,
            tracestate=None,
        )
        self.pending_event: ClaimedEvent | None = None
        self.envelope: dict[str, Any] | None = None
        self.job_failure: Exception | None = None
        self.projection_destination: str | None = None
        self.loaded_records = 0

    def claim_job(self, worker_name: str) -> ClaimedJob | None:
        del worker_name
        job, self.job = self.job, None
        return job

    def load_record(self, feedback_id: str) -> FeedbackRecord:
        assert feedback_id == self.record.feedback_id
        self.loaded_records += 1
        return self.record

    def persist_success(
        self,
        job: ClaimedJob,
        envelope: dict[str, Any],
        event: dict[str, Any],
        *,
        traceparent: str | None = None,
        tracestate: str | None = None,
    ) -> None:
        del job
        self.envelope = envelope
        self.pending_event = ClaimedEvent(
            event_id=str(event["event_id"]),
            lease_token="00000000-0000-0000-0000-000000000012",
            attempt_count=1,
            payload=event,
            traceparent=traceparent,
            tracestate=tracestate,
        )

    def persist_failure(self, job: ClaimedJob, error: Exception) -> None:
        del job
        self.job_failure = error

    def claim_event(self, worker_name: str) -> ClaimedEvent | None:
        del worker_name
        event, self.pending_event = self.pending_event, None
        return event

    def persist_projection_success(self, event: ClaimedEvent, destination: str) -> None:
        del event
        self.projection_destination = destination

    def persist_projection_failure(self, event: ClaimedEvent, error: Exception) -> None:
        del event
        raise AssertionError("projection should not fail") from error


class FakeProjector:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def insert_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)
