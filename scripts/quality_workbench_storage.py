"""Scoped lease, immutable snapshot and replay tests inside the workbench runtime."""

from __future__ import annotations

import json
from uuid import uuid4

import psycopg

from feedback_intelligence_worker.workbench.analysis import rule_classify
from feedback_intelligence_worker.workbench.imports import parse_upload, validate_import
from feedback_intelligence_worker.workbench.repository import Repository
from feedback_intelligence_worker.workbench.server import secret


def main() -> None:
    with (
        Repository(secret("WORKBENCH_API_DSN")) as api,
        Repository(secret("WORKBENCH_WORKER_DSN")) as worker,
    ):
        data = validate_import(
            parse_upload(b"text\nGreat support\nPoor quality\n", "checks.csv"),
            {"mapping": {"text": "text"}, "language": "en"},
        )
        dataset = api.import_dataset("Scoped storage acceptance", data)
        template = next(t for t in api.templates() if t["name"] == "General feedback")
        with api.db.transaction():
            run = api.create_run(
                {
                    "datasetId": str(dataset["id"]),
                    "templateId": str(template["id"]),
                    "engine": "rules",
                    "mode": "sample",
                    "idempotencyKey": str(uuid4()),
                }
            )
            api.db.execute("UPDATE workbench.runs SET status='paused' WHERE id=%s", (run["id"],))
        identity = str(run["id"])
        # Hold the run lock throughout controlled claims; the live service skips it.
        with worker.db.transaction():
            worker.db.execute("UPDATE workbench.runs SET status='queued' WHERE id=%s", (run["id"],))
            first = worker.claim(identity)
            assert first is not None
            second = worker.claim(identity)
            assert second is not None and second["record"]["id"] != first["record"]["id"]
            result = rule_classify(first["record"], first["snapshot"]["template"])
            result["templateRevision"] = first["snapshot"]["templateRevision"]
            assert not worker.finish({**first, "lease": str(uuid4())}, result), (
                "Stale owner committed"
            )
            worker.db.execute(
                "UPDATE workbench.jobs SET leased_until=now()-interval '1 second' WHERE run_id=%s",
                (run["id"],),
            )
            assert not worker.finish(first, result), "Expired lease committed"
            assert worker.claim(identity) is None
            assert worker.run(identity)["status"] == "paused"
        with worker.db.transaction():
            worker.change_run(identity, "resume")
            current = worker.claim(identity)
            assert current is not None and current["lease"] != first["lease"]
            result = rule_classify(current["record"], current["snapshot"]["template"])
            result["templateRevision"] = current["snapshot"]["templateRevision"]
            assert worker.finish(current, result)
            try:
                with worker.db.transaction():
                    worker.db.execute(
                        "UPDATE workbench.results SET payload='{}' WHERE run_id=%s", (run["id"],)
                    )
            except psycopg.Error:
                pass
            else:
                raise AssertionError("Worker edited immutable results")
            worker.db.execute(
                "UPDATE workbench.jobs SET status='failed',error_code='test_refusal' "
                "WHERE run_id=%s AND status='pending'",
                (run["id"],),
            )
            worker.db.execute(
                "UPDATE workbench.runs SET status='completed',completed_at=now() WHERE id=%s",
                (run["id"],),
            )
        try:
            api.db.execute("DELETE FROM workbench.results WHERE run_id=%s", (run["id"],))
        except psycopg.errors.InsufficientPrivilege:
            pass
        else:
            raise AssertionError("API bypassed the dedicated purge role")
        with api.db.transaction():
            full = api.create_run(
                {
                    "datasetId": str(dataset["id"]),
                    "templateId": str(template["id"]),
                    "engine": "rules",
                    "mode": "full",
                    "idempotencyKey": str(uuid4()),
                    "sampleRunId": identity,
                }
            )
            api.db.execute("UPDATE workbench.runs SET status='paused' WHERE id=%s", (full["id"],))
        copied = api.result_rows(str(full["id"]))
        assert len(copied) == 1 and copied[0]["result"]["reusedFromRun"] == identity
        assert len(api.result_rows(identity)) == 1
        # Mocked AI settings exercise persistence/reuse, never provider inference.
        ai_options = {
            "datasetId": str(dataset["id"]),
            "templateId": str(template["id"]),
            "engine": "openai",
            "mode": "sample",
            "connectionId": str(uuid4()),
            "model": "gpt-6.1-sol",
            "reasoningEffort": "high",
            "externalConsent": True,
            "idempotencyKey": str(uuid4()),
        }
        with api.db.transaction():
            ai = api.create_run(ai_options)
            api.db.execute("UPDATE workbench.runs SET status='paused' WHERE id=%s", (ai["id"],))
            assert api.create_run(ai_options)["id"] == ai["id"]
        with worker.db.transaction():
            worker.change_run(str(ai["id"]), "resume")
            claim = worker.claim(str(ai["id"]))
            assert claim is not None and claim["snapshot"]["reasoningEffort"] == "high"
            answer = rule_classify(claim["record"], claim["snapshot"]["template"])
            answer.update(
                templateRevision=claim["snapshot"]["templateRevision"], reasoningEffort="high"
            )
            assert worker.finish(claim, answer)
            worker.db.execute(
                "UPDATE workbench.jobs SET status='failed' WHERE run_id=%s AND status='pending'",
                (ai["id"],),
            )
            worker.db.execute(
                "UPDATE workbench.runs SET status='completed' WHERE id=%s", (ai["id"],)
            )
        try:
            api.create_run({**ai_options, "reasoningEffort": "medium"})
        except ValueError:
            pass
        else:
            raise AssertionError("Changed effort reused an idempotency key")
        try:
            api.create_run(
                {
                    **ai_options,
                    "mode": "full",
                    "sampleRunId": str(ai["id"]),
                    "reasoningEffort": "medium",
                    "idempotencyKey": str(uuid4()),
                }
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Different-effort sample was reused")
        with api.db.transaction():
            expanded = api.create_run(
                {
                    **ai_options,
                    "mode": "full",
                    "sampleRunId": str(ai["id"]),
                    "idempotencyKey": str(uuid4()),
                }
            )
            api.db.execute(
                "UPDATE workbench.runs SET status='paused' WHERE id=%s", (expanded["id"],)
            )
        assert api.result_rows(str(expanded["id"]))[0]["result"]["reasoningEffort"] == "high"
        api.mark_delete(str(dataset["id"]))
        print(
            "Scoped storage passed: distinct claims, expiry, fencing, immutable results, "
            "role separation and sample reuse"
        )
        print(json.dumps({"datasetPendingPurge": str(dataset["id"])}))


if __name__ == "__main__":
    main()
