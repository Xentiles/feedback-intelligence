"""Build and smoke-test current demo web/API source in isolated Docker resources.

Run: services/decision-worker/.venv/bin/python scripts/quality_demo_check.py
No .env, application database, browser, or model provider is used. Writes only a
sanitized HTTP timing report, then removes this invocation's containers/network/tags.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/quality/http-performance.json"
API_PREFIX = "/api/v1/dashboard"
WARM_REQUESTS = 100


def docker(*arguments: str) -> str:
    return subprocess.check_output(["docker", *arguments], text=True).strip()


def require(condition: bool, description: str) -> None:
    if not condition:
        raise AssertionError(description)


def fetch(base_url: str, path: str) -> tuple[dict[str, Any], bytes]:
    request = urllib.request.Request(base_url + path, headers={"Connection": "close"})
    started = time.perf_counter_ns()
    try:
        response = urllib.request.urlopen(request, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read()
        status = response.status
    duration_ms = (time.perf_counter_ns() - started) / 1_000_000
    return {
        "duration_ms": duration_ms,
        "status": status,
        "response_bytes": len(body),
    }, body


def get_json(
    base_url: str, path: str, status: int = 200
) -> tuple[dict[str, Any], dict[str, Any]]:
    sample, body = fetch(base_url, path)
    require(
        sample["status"] == status,
        f"{path}: expected HTTP {status}, got {sample['status']}",
    )
    value: dict[str, Any] = json.loads(body)
    require(isinstance(value, dict), "JSON response was not an object")
    return sample, value


def path(endpoint: str, **query: str | int) -> str:
    return f"{API_PREFIX}{endpoint}?{urllib.parse.urlencode(query)}"


def summarize(base_url: str, endpoint: str, first: dict[str, Any]) -> dict[str, Any]:
    samples = []
    for _ in range(WARM_REQUESTS):
        sample, _body = fetch(base_url, endpoint)
        require(sample["status"] == 200, f"warm request failed for {endpoint}")
        require(
            sample["response_bytes"] == first["response_bytes"], "response size changed"
        )
        samples.append(sample)
    durations = sorted(float(sample["duration_ms"]) for sample in samples)
    return {
        "path": endpoint,
        "first_request": first,
        "warm_request_count": WARM_REQUESTS,
        "warm_summary_ms": {
            "min": durations[0],
            "median": statistics.median(durations),
            "p95_nearest_rank": durations[math.ceil(0.95 * len(durations)) - 1],
            "max": durations[-1],
        },
        "warm_samples": samples,
    }


def smoke_and_measure(api_url: str, web_url: str) -> dict[str, Any]:
    checks = []
    api_health, api_body = fetch(api_url, "/health")
    web_health, web_body = fetch(web_url, "/health")
    require(api_health["status"] == 200 and b"Healthy" in api_body, "API health failed")
    require(web_health["status"] == 200 and b"healthy" in web_body, "web health failed")
    home, html = fetch(web_url, "/")
    require(
        home["status"] == 200 and b'<div id="root">' in html, "SPA document missing"
    )
    require(b"/assets/" in html, "compiled SPA assets missing")
    checks.append("API/web health and compiled SPA HTML: HTTP 200")

    _, metadata = get_json(web_url, path("/metadata", context="demo"))
    fixtures = []
    for name in (
        "dashboard-demo.json",
        "dashboard-demo-semif.json",
        "dashboard-demo-rules.json",
    ):
        fixture_path = (
            ROOT / "services/api/src/FeedbackIntelligence.Api/Fixtures" / name
        )
        fixtures.append(json.loads(fixture_path.read_text()))
    expected_keys = {fixture["source"]["key"] for fixture in fixtures}
    require(
        {source["key"] for source in metadata["sources"]} == expected_keys,
        "metadata source options differ from current fixture source",
    )
    selected = next(
        fixture
        for fixture in fixtures
        if fixture["source"]["key"] == metadata["source"]["key"]
    )
    expected_times = sorted(
        datetime.fromisoformat(record["occurredAt"]) for record in selected["records"]
    )
    date_range = metadata["availableRange"]
    require(
        datetime.fromisoformat(date_range["from"]) == expected_times[0],
        "range start differs",
    )
    require(
        datetime.fromisoformat(date_range["toExclusive"])
        == expected_times[-1] + timedelta(milliseconds=1),
        "range end differs",
    )
    require(len(selected["records"]) == 480, "unexpected fixture size")
    checks.append(
        "Nginx API proxy, three demo sources, exact fixture range and 480 records"
    )

    query = {"context": "demo", "sourceKey": metadata["source"]["key"], **date_range}
    overview_path = path("/overview", **query)
    first_overview, overview = get_json(web_url, overview_path)
    require(
        overview["processing"]["feedbackRecords"] == 480,
        "overview record count differs",
    )
    signal = next(item for item in overview["signals"] if item["numerator"] > 0)
    signal_path = f"/signals/{signal['id']}"
    _, detail = get_json(web_url, path(signal_path, **query))
    require(detail["signal"] == signal, "signal does not match overview")
    evidence_path = path(signal_path + "/evidence", **query, page=1, pageSize=10)
    first_evidence, evidence = get_json(web_url, evidence_path)
    require(
        evidence["total"] == signal["numerator"],
        "evidence total differs from numerator",
    )
    require(
        len(evidence["items"]) == min(10, evidence["total"]),
        "evidence page size differs",
    )
    item = evidence["items"][0]
    _, evidence_detail = get_json(
        web_url,
        path(
            f"/evidence/{item['feedbackId']}",
            context="demo",
            decisionId=item["decisionId"],
        ),
    )
    require(
        evidence_detail["record"]["feedbackId"] == item["feedbackId"],
        "feedback mismatch",
    )
    require(
        evidence_detail["provenance"]["decisionId"] == item["decisionId"],
        "decision mismatch",
    )
    require(
        evidence_detail["evidence"]["access"] == "permitted_synthetic",
        "wrong evidence access",
    )
    require(bool(evidence_detail["evidence"]["body"]), "synthetic evidence body absent")
    require(len(evidence_detail["answers"]) == 14, "typed answer count differs")
    checks.append(
        "Overview → signal → paginated evidence → immutable decision detail agrees"
    )

    for invalid in (
        {"page": 0},
        {"page": -1},
        {"page": "bad"},
        {"pageSize": 51},
        {"page": 2147483647, "pageSize": 50},
    ):
        get_json(web_url, path(signal_path + "/evidence", **query, **invalid), 400)
    product_query = {**query, "product": metadata["filterOptions"]["products"][0]}
    get_json(web_url, path(signal_path + "/evidence", **product_query, page=0), 400)
    get_json(
        web_url, path("/overview", **{**query, "sourceKey": "missing/source"}), 404
    )
    get_json(web_url, path("/metadata", context="invalid"), 400)
    checks.append(
        "Invalid paging, overflowing paging, changed-product invalid page and source/context errors"
    )

    get_json(api_url, path("/metadata", context="live"), 503)
    get_json(web_url, path("/overview", **{**query, "context": "live"}), 503)
    _, live_trends = get_json(web_url, path("/trends", context="live"))
    require(
        live_trends["availability"]
        == {"state": "unavailable", "reason": "awaiting_calibration"},
        "live trends were not withheld",
    )
    require(live_trends["results"] == [], "uncalibrated live trends returned results")
    _, live_evaluation = get_json(web_url, path("/evaluation", context="live"))
    require(
        live_evaluation["availability"]["reason"] == "awaiting_human_labels",
        "live evaluation was not withheld",
    )
    checks.append(
        "No-database live metadata/overview unavailable; trends/evaluation withheld"
    )

    trends_path = path("/trends", context="demo")
    first_trends, trends = get_json(web_url, trends_path)
    require(trends["availability"]["state"] == "available", "demo trends unavailable")
    require(
        trends["source"]["synthetic"] is True,
        "trend fixture lost synthetic attribution",
    )
    checks.append("Frozen demo trends remain explicitly synthetic")
    measured = {
        "overview": summarize(web_url, overview_path, first_overview),
        "evidence": summarize(web_url, evidence_path, first_evidence),
        "trends": summarize(web_url, trends_path, first_trends),
    }
    return {
        "schema_version": "quality-http-performance/1.0.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "checks_passed": checks,
        "fixture": {
            "overview_evidence_record_count": 480,
            "source_key": metadata["source"]["key"],
            "source_count": len(expected_keys),
            "selected_signal": signal["id"],
            "selected_signal_numerator": signal["numerator"],
            "trend_source_key": trends["source"]["key"],
            "dashboard_fixture_sha256": hashlib.sha256(
                json.dumps(selected, sort_keys=True).encode()
            ).hexdigest(),
        },
        "environment": {
            "host_os": platform.system(),
            "host_machine": platform.machine(),
            "host_logical_cpu_count": os.cpu_count(),
            "python_version": platform.python_version(),
            "transport": "host loopback HTTP/1.1 → isolated Docker Nginx → isolated ASP.NET API",
            "connections": "one new HTTP connection per request; sequential, no concurrency",
            "databases": "none configured; no model/provider calls",
        },
        "limitations": [
            "One local host with synthetic fixtures; not an SLA or production capacity test.",
            "Overview/evidence use 480 records; trends use a separate frozen backtest fixture.",
            "First request is the first measured call to that route after health/metadata "
            "discovery, not a cold process.",
            "Warm samples include host networking, new connections, proxying and body reads.",
            "No browser, database/provider latency, concurrency or deployment network measured.",
            "p95 uses nearest-rank: sorted sample at ceil(0.95 * 100), separate from median.",
            "Runtime resources and unique image tags removed; shared build cache retained.",
        ],
        "routes": measured,
    }


def main() -> None:
    suffix = uuid4().hex[:12]
    network_name = f"feedback-demo-quality-{suffix}"
    images: list[str] = []
    containers: list[str] = []
    network_id = ""
    try:
        for service, context in (("api", "services/api"), ("web", "apps/web")):
            tag = f"feedback-demo-quality-{service}:{suffix}"
            print(f"Building current {service} source", flush=True)
            subprocess.run(
                [
                    "docker",
                    "build",
                    "--pull=false",
                    "--tag",
                    tag,
                    "--file",
                    str(ROOT / context / "Dockerfile"),
                    str(ROOT),
                ],
                check=True,
                timeout=300,
            )
            images.append(tag)
        network_id = docker("network", "create", network_name)
        for service, image in zip(("api", "web"), images, strict=True):
            container_id = docker(
                "run",
                "--detach",
                "--rm",
                "--pull=never",
                "--name",
                f"{network_name}-{service}",
                "--network",
                network_name,
                "--network-alias",
                service,
                "--publish",
                "127.0.0.1::8080",
                "--env",
                "ASPNETCORE_ENVIRONMENT=Production",
                "--env",
                "Ingestion__Enabled=false",
                "--env",
                "Observability__Enabled=false",
                image,
            )
            containers.append(container_id)
        ports = [
            docker("port", identity, "8080/tcp").rsplit(":", 1)[1]
            for identity in containers
        ]
        urls = [f"http://127.0.0.1:{port}" for port in ports]
        deadline = time.monotonic() + 60
        for url in urls:
            while True:
                try:
                    sample, _ = fetch(url, "/health")
                    if sample["status"] == 200:
                        break
                except (urllib.error.URLError, ConnectionError):
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError("isolated service did not become healthy")
                time.sleep(0.25)
        report = smoke_and_measure(*urls)
        report["environment"]["built_image_ids"] = {
            service: docker("image", "inspect", "--format", "{{.Id}}", tag)
            for service, tag in zip(("api", "web"), images, strict=True)
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(
            f"PASS: {len(report['checks_passed'])} HTTP smoke groups; 100 warm samples per route",
            flush=True,
        )
        for route, result in report["routes"].items():
            print(
                f"{route}: {json.dumps(result['warm_summary_ms'], sort_keys=True)}",
                flush=True,
            )
        print(f"Wrote {OUTPUT.relative_to(ROOT)}", flush=True)
    finally:
        for container_id in reversed(containers):
            docker("rm", "--force", container_id)
        if network_id:
            docker("network", "rm", network_id)
        for tag in reversed(images):
            docker("image", "rm", tag)
        print(
            "Removed this invocation's containers, network and image tags", flush=True
        )


if __name__ == "__main__":
    main()
