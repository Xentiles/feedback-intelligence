"""Authenticated internal import/processing service behind the public .NET API."""

from __future__ import annotations

import base64
import csv
import hmac
import io
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from feedback_intelligence_worker.data.config import find_repository_root
from feedback_intelligence_worker.privacy.models import PrivacyBoundaryError
from feedback_intelligence_worker.synthetic.generator import SyntheticDatasetGenerator
from feedback_intelligence_worker.synthetic.spec import load_generator_spec
from feedback_intelligence_worker.workbench import openai
from feedback_intelligence_worker.workbench.analysis import (
    DETECTOR_IMPLEMENTATION,
    PROTOCOL_HASH,
    filter_rows,
    normalize_filters,
    observed_facets,
    prepare,
    rule_classify,
    sample_records,
    summarize,
    trends,
)
from feedback_intelligence_worker.workbench.imports import MAX_BYTES, parse_upload, validate_import
from feedback_intelligence_worker.workbench.repository import Repository

UPLOADS: dict[str, tuple[float, dict[str, Any]]] = {}
UPLOAD_LOCK = threading.Lock()


def environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def secret(name: str) -> str:
    path = os.getenv(f"{name}_FILE")
    return Path(path).read_text().strip() if path else environment(name)


def api_dsn() -> str:
    return secret("WORKBENCH_API_DSN")


def fetch_json(url: str, payload: dict[str, Any] | None = None) -> Any:
    request = urllib.request.Request(
        url,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {secret('WORKBENCH_SERVICE_TOKEN')}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        raise openai.ProviderFailure(f"connection_http_{status}", True) from None
    except urllib.error.URLError:
        raise openai.ProviderFailure("connection_unavailable", True) from None


def upload(identity: str) -> dict[str, Any]:
    with UPLOAD_LOCK:
        value = UPLOADS.get(identity)
        if not value or value[0] < time.monotonic():
            UPLOADS.pop(identity, None)
            raise ValueError("Upload preview expired; upload again")
        return value[1]


def handle(method: str, path: str, data: dict[str, Any], query: dict[str, list[str]]) -> Any:
    parts = path.strip("/").split("/")
    if path == "/imports/preview" and method == "POST":
        if len(str(data.get("content", ""))) > MAX_BYTES * 4 // 3 + 8:
            raise ValueError("Upload exceeds 25 MiB")
        content = base64.b64decode(data["content"], validate=True)
        value = parse_upload(
            content, str(data.get("filename", "feedback.txt")), int(data.get("sheet", 0))
        )
        identity = str(uuid4())
        with UPLOAD_LOCK:
            for key in list(UPLOADS):
                if UPLOADS[key][0] < time.monotonic():
                    del UPLOADS[key]
            if len(UPLOADS) >= 4:
                raise ValueError("Finish an existing upload or wait for its ten-minute expiry")
            UPLOADS[identity] = (time.monotonic() + 600, value)
        return {
            "uploadId": identity,
            "columns": value["columns"],
            "sheets": value["sheets"],
            "rows": [
                {key: str(cell)[:500] for key, cell in row.items()} for row in value["rows"][:10]
            ],
            "total": len(value["rows"]),
        }
    if path in ("/imports/validate", "/imports/commit") and method == "POST":
        value = validate_import(upload(data["uploadId"]), data["options"])
        if path.endswith("validate"):
            prepared: list[dict[str, Any]] = []
            blocked = 0
            for record in value["records"]:
                try:
                    text, _, redactions = prepare(record)
                    if len(prepared) < 5:
                        prepared.append(
                            {
                                "row": record["position"],
                                "redactedText": text,
                                "redactions": redactions,
                            }
                        )
                except PrivacyBoundaryError:
                    blocked += 1
            return {**value, "records": [], "privacyPreview": prepared, "blocked": blocked}
        if data.get("acceptExclusions") is not True:
            raise ValueError("Confirm the validation summary before importing")
        with Repository(api_dsn()) as repository:
            result = repository.import_dataset(data["name"], value)
        with UPLOAD_LOCK:
            UPLOADS.pop(data["uploadId"], None)
        return result
    with Repository(api_dsn()) as repository:
        if path == "/datasets/demo" and method == "POST":
            generated = SyntheticDatasetGenerator(
                load_generator_spec(find_repository_root() / "data/synthetic/generator-v1.yaml")
            ).generate(record_count=10_000)
            demo_rows: list[dict[str, Any]] = [
                {
                    "id": r.feedback_id,
                    "text": r.original_text,
                    "date": r.occurred_at.isoformat(),
                    "language": r.language,
                    "channel": r.channel,
                    "rating": None if r.rating is None else float(r.rating.value),
                    "product": r.related_products[0].product_name if r.related_products else "",
                }
                for r in generated.records
            ]
            source = parse_upload(json.dumps(demo_rows).encode(), "synthetic.json")
            value = validate_import(
                source,
                {
                    "mapping": {
                        "text": "text",
                        "id": "id",
                        "date": "date",
                        "language": "language",
                        "channel": "channel",
                        "rating": "rating",
                        "product": "product",
                    },
                    "ratingMin": 1,
                    "ratingMax": 5,
                },
            )
            return repository.import_dataset("10,000 synthetic reviews - rules scenario", value)
        if path == "/datasets" and method == "GET":
            return list(
                repository.db.execute(
                    "SELECT d.*, (SELECT count(*) FROM workbench.records r WHERE "
                    "r.dataset_id=d.id) AS count FROM workbench.datasets d W"
                    "HERE status<>'deleted' "
                    "ORDER BY created_at DESC"
                )
            )
        if len(parts) == 2 and parts[0] == "datasets":
            if method == "DELETE":
                repository.mark_delete(parts[1])
                return {"status": "deleting"}
            return repository.dataset(parts[1])
        if path == "/templates":
            return repository.templates() if method == "GET" else repository.save_template(data)
        if path == "/runs/preview" and method == "POST":
            records = repository.records(data["datasetId"])
            selected = sample_records(records) if data.get("mode") == "sample" else records
            reused: set[str] = set()
            if data.get("sampleRunId"):
                parent = repository.run(data["sampleRunId"])
                if str(parent["dataset_id"]) != data["datasetId"]:
                    raise ValueError("Sample belongs to another dataset")
                reused = {row["id"] for row in repository.result_rows(data["sampleRunId"])}
            selected = [row for row in selected if row["id"] not in reused]
            examples: list[dict[str, Any]] = []
            blocked = 0
            for row in selected:
                try:
                    text, _, redactions = prepare(row)
                    if len(examples) < 5:
                        examples.append(
                            {"row": row["position"], "redactedText": text, "redactions": redactions}
                        )
                except PrivacyBoundaryError:
                    blocked += 1
            return {
                "selected": len(selected),
                "blocked": blocked,
                "reused": len(reused),
                "prepared": examples,
            }
        if path == "/runs":
            if method == "GET":
                return [
                    repository.run(str(r["id"]))
                    for r in repository.db.execute(
                        "SELECT r.id FROM workbench.runs r JOIN workbench.datasets d ON "
                        "d.id=r.dataset_id WHERE d.status='ready' ORDER BY r.cre"
                        "ated_at DESC LIMIT 100"
                    )
                ]
            if data.get("engine") == "openai":
                connection = fetch_json(
                    environment("WORKBENCH_BROKER_URL") + "/internal/workbench/validate-connection",
                    {"connectionId": data.get("connectionId"), "model": data.get("model")},
                )
                data["billingMode"] = connection["billingMode"]
            return repository.create_run(data)
        if len(parts) >= 2 and parts[0] == "runs":
            if len(parts) == 2:
                return repository.run(parts[1])
            action = parts[2]
            if action in ("cancel", "resume") and method == "POST":
                run = repository.run(parts[1])
                if (
                    action == "resume"
                    and run["snapshot"]["engine"] == "openai"
                    and data.get("externalConsent") is not True
                ):
                    raise ValueError(
                        "Confirm resume: interrupted requests may consume additional usage"
                    )
                return repository.change_run(parts[1], action)
            selected_filters = normalize_filters(query)
            if action == "trends" and selected_filters["topic"]:
                raise ValueError(
                    "Clear the topic filter before trend analysis "
                    "to preserve topic-rate denominators"
                )
            read_at = datetime.now(UTC).isoformat()
            run, all_rows, pending = repository.result_snapshot(parts[1])
            run_usage = summarize(all_rows, run["target"])
            rows = filter_rows(all_rows, selected_filters)
            if action == "results":
                page_size = 50
                page = min(
                    max(1, int(query.get("page", ["1"])[0])),
                    max(1, (len(rows) + page_size - 1) // page_size),
                )
                page_rows = rows[(page - 1) * page_size : page * page_size]
                return {
                    "run": run,
                    "runUsage": run_usage,
                    "summary": summarize(rows, run["target"]),
                    "rows": [{**row, "text": row["result"]["redactedText"]} for row in page_rows],
                    "page": page,
                    "readAt": read_at,
                    "pageSize": page_size,
                    "returned": len(page_rows),
                    "filtered": len(rows),
                    "filters": selected_filters,
                    "facets": observed_facets(all_rows, run["snapshot"]["template"]),
                    "groups": {
                        key: sorted(
                            {str(r["groups"][key]) for r in all_rows if r["groups"].get(key)}
                        )
                        for key in ("product", "group")
                    },
                    "projectionPending": pending,
                }
            if action == "trends":
                return trends(
                    rows, query.get("method", ["simple_rate_change"])[0], selected_filters
                )
            if action == "export":
                original = query.get("original", ["false"])[0] == "true"
                exported = [
                    {**row, "text": row["text"] if original else row["result"]["redactedText"]}
                    for row in rows
                ]
                document = {
                    "schemaVersion": "workbench-export/1.0.0",
                    "run": run,
                    "summary": summarize(rows, run["target"]),
                    "originalTextIncluded": original,
                    "filters": selected_filters,
                    "analysisImplementation": DETECTOR_IMPLEMENTATION,
                    "records": exported,
                }
                if query.get("format", ["json"])[0] == "csv":
                    output = io.StringIO()
                    fields = [
                        "record_id",
                        "source_id",
                        "date",
                        "language",
                        "text",
                        "topic",
                        "sentiment",
                        "actionable",
                        "run_id",
                        "dataset_snapshot",
                        "template_revision",
                        "requested_model",
                        "resolved_model",
                        "protocol_hash",
                        "analysis_implementation",
                        "filters",
                    ]
                    writer = csv.DictWriter(output, fieldnames=fields)
                    writer.writeheader()
                    for row in exported:
                        values = [
                            row["id"],
                            row["sourceId"],
                            row["occurredAt"],
                            row["language"],
                            row["text"],
                            row["result"]["topic"],
                            row["result"]["sentiment"],
                            row["result"]["actionable"],
                            parts[1],
                            run["snapshot"]["datasetSnapshot"],
                            run["snapshot"]["templateRevision"],
                            row["result"]["requestedModel"],
                            row["result"]["resolvedModel"],
                            PROTOCOL_HASH,
                            DETECTOR_IMPLEMENTATION,
                            json.dumps(selected_filters, sort_keys=True),
                        ]
                        writer.writerow(
                            {
                                key: "'" + str(value)
                                if str(value).lstrip().startswith(("=", "+", "-", "@"))
                                else value
                                for key, value in zip(fields, values, strict=True)
                            }
                        )
                    return {"filename": "classifications.csv", "content": output.getvalue()}
                return {
                    "filename": "classifications.json",
                    "content": json.dumps(document, default=str, ensure_ascii=False, indent=2),
                }
        if path == "/compare" and method == "POST":
            left, right = repository.run(data["left"]), repository.run(data["right"])
            if left["dataset_id"] != right["dataset_id"] or any(
                left["snapshot"][key] != right["snapshot"][key]
                for key in ("datasetSnapshot", "templateRevision", "protocolHash", "privacyVersion")
            ):
                raise ValueError(
                    "Comparison requires the same dataset, template and analysis protocol"
                )
            a, b = (
                {r["id"]: r for r in repository.result_rows(data["left"])},
                {r["id"]: r for r in repository.result_rows(data["right"])},
            )
            shared = sorted(a.keys() & b.keys())
            differences = [
                {
                    "recordId": key,
                    "text": a[key]["result"]["redactedText"],
                    "left": a[key]["result"],
                    "right": b[key]["result"],
                }
                for key in shared
                if any(
                    a[key]["result"][field] != b[key]["result"][field]
                    for field in ("topic", "sentiment", "actionable")
                )
            ]
            return {
                "shared": len(shared),
                "leftProcessed": len(a),
                "rightProcessed": len(b),
                "agreement": None if not shared else 1 - len(differences) / len(shared),
                "disagreements": differences[:100],
                "disagreementCount": len(differences),
                "label": "Classification agreement, not accuracy",
            }
    raise LookupError("Endpoint does not exist")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_: object) -> None:
        pass  # No URLs, bodies or headers enter server logs.

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"healthy")
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        expected = f"Bearer {secret('WORKBENCH_SERVICE_TOKEN')}"
        if not hmac.compare_digest(self.headers.get("Authorization", ""), expected):
            self.send_error(401)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 36 * 1024 * 1024:
                raise ValueError("Request exceeds limit")
            request = json.loads(self.rfile.read(size))
            value = handle(
                request["method"],
                request["path"],
                request.get("body", {}),
                request.get("query", {}),
            )
            self.reply(200, value)
        except (ValueError, KeyError, TypeError) as error:
            self.reply(
                400,
                {
                    "error": str(error)
                    if isinstance(error, ValueError)
                    else "Invalid request fields"
                },
            )
        except LookupError:
            self.reply(404, {"error": "Resource not found"})
        except openai.ProviderFailure as error:
            self.reply(409, {"error": error.code})
        except Exception:
            self.reply(503, {"error": "Workbench temporarily unavailable"})

    def reply(self, status: int, value: Any) -> None:
        content = json.dumps(value, default=str, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def project_and_purge(repository: Repository) -> None:
    url = environment("CLICKHOUSE_URL")
    credentials = base64.b64encode(
        f"{environment('CLICKHOUSE_USER')}:{secret('CLICKHOUSE_PASSWORD')}".encode()
    ).decode()
    deleting = list(
        repository.db.execute("SELECT id FROM workbench.datasets WHERE status='deleting'")
    )
    for dataset in deleting:
        identity = str(dataset["id"])
        active = repository.one(
            "SELECT EXISTS(SELECT 1 FROM workbench.jobs j JOIN workbench.runs r ON r.id=j.run_id "
            "WHERE r.dataset_id=%s AND j.status='running' AND j.leased_until>now()) OR "
            "EXISTS(SELECT 1 FROM workbench.outbox WHERE dataset_id=%s "
            "AND status='publishing' AND leased_until>now()) AS busy",
            (identity, identity),
        )
        if active["busy"]:
            continue
        sql = (
            "ALTER TABLE feedback_intelligence.workbench_classifications DELETE "
            f"WHERE dataset_id='{UUID(identity)}' SETTINGS mutations_sync=2"
        )
        request = urllib.request.Request(
            url, data=sql.encode(), headers={"Authorization": f"Basic {credentials}"}
        )
        with urllib.request.urlopen(request, timeout=60):
            pass
        with Repository(secret("WORKBENCH_PURGE_DSN")) as purger:
            purger.purge(identity)
    with repository.db.transaction():
        events = repository.db.execute(
            "SELECT o.* FROM workbench.outbox o JOIN workbench.datasets d ON "
            "d.id=o.dataset_id WHERE d.status='ready' AND (o.status='pending' OR "
            "(o.status='publishing' AND o.leased_until<now())) AND o.attempt<8 ORDER BY "
            "o.id FOR UPDATE OF o SKIP LOCKED LIMIT 100"
        ).fetchall()
        if not events:
            return
        token = uuid4()
        event_ids = [event["id"] for event in events]
        repository.db.execute(
            (
                "UPDATE workbench.outbox SET "
                "status='publishing',lease_token=%s,leased_until=now()+interval '90 "
                "seconds',attempt=attempt+1 WHERE id=ANY(%s)"
            ),
            (token, event_ids),
        )
    # A single processing loop owns classification, projection and purge ordering.
    request = urllib.request.Request(
        url + "?date_time_input_format=best_effort",
        data=(
            "INSERT INTO feedback_intelligence.workbench_classifications FORMAT JSONEachRow\n"
            + "\n".join(json.dumps(event["payload"], default=str) for event in events)
        ).encode(),
        headers={"Authorization": f"Basic {credentials}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30):
            pass
        repository.db.execute(
            (
                "UPDATE workbench.outbox SET status='published',lease_token=NULL WHERE id=ANY(%s) "
                "AND lease_token=%s"
            ),
            (event_ids, token),
        )
    except (urllib.error.URLError, TimeoutError):
        repository.db.execute(
            (
                "UPDATE workbench.outbox SET status=CASE WHEN attempt>=8 THEN 'dead' ELSE "
                "'pending' END,error_code='projection_failed',lease_token=NULL WHERE id=ANY(%s) "
                "AND "
                "lease_token=%s"
            ),
            (event_ids, token),
        )


def process_job(repository: Repository, job: dict[str, Any]) -> None:
    try:
        snapshot = job["snapshot"]
        if snapshot["engine"] == "rules":
            result = rule_classify(job["record"], snapshot["template"])
        else:
            credential = fetch_json(
                environment("WORKBENCH_BROKER_URL") + "/internal/workbench/credential",
                {"runId": str(job["id"]), "connectionId": snapshot["connectionId"]},
            )

            def active() -> bool:
                return bool(repository.run(str(job["id"]))["status"] == "running")

            result = openai.classify(
                job["record"],
                snapshot["template"],
                snapshot["model"],
                credential["token"],
                active,
                credential["mode"],
            )
        result["templateRevision"] = snapshot["templateRevision"]
        repository.finish(job, result)
    except openai.ProviderFailure as error:
        repository.finish(job, None, error.code, error.pause)
    except PrivacyBoundaryError:
        repository.finish(job, None, "privacy_blocked")
    except Exception:
        repository.finish(job, None, "classification_failed")


def worker() -> None:
    while True:
        try:
            with Repository(secret("WORKBENCH_WORKER_DSN")) as repository:
                while True:
                    project_and_purge(repository)
                    did_work = False
                    for _ in range(20):
                        job = repository.claim()
                        if not job:
                            break
                        did_work = True
                        process_job(repository, job)
                    if not did_work:
                        time.sleep(0.25)
        except Exception:
            # Body-free recovery: database/collector details may contain secrets.
            time.sleep(2)


def main() -> None:
    secret("WORKBENCH_SERVICE_TOKEN")
    threading.Thread(target=worker, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
