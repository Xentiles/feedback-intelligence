"""Provision protected local credentials and start the isolated workbench."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".workbench-runtime"


def save(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(content)


def main() -> None:
    environment = RUNTIME / "environment"
    if not environment.exists():
        admin, clickhouse, api, worker, purge = [secrets.token_hex(24) for _ in range(5)]
        service, owner = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        save(
            environment,
            f"WORKBENCH_UID={os.getuid()}\nWORKBENCH_GID={os.getgid()}\nWORKBENCH_POSTGRES_PASSWORD={admin}\nWORKBENCH_CLICKHOUSE_PASSWORD={clickhouse}\n",
        )

        def dsn(name: str, password: str) -> str:
            return f"postgresql://{name}:{password}@postgres:5432/feedback_intelligence"

        save(RUNTIME / "api" / "owner-code", owner)
        save(RUNTIME / "api" / "service-token", service)
        save(
            RUNTIME / "api" / "database",
            f"Host=postgres;Database=feedback_intelligence;Username=workbench_api_login;Password={api}",
        )
        for name, value in [
            ("service-token", service),
            ("api-dsn", dsn("workbench_api_login", api)),
            ("worker-dsn", dsn("workbench_worker_login", worker)),
            ("purge-dsn", dsn("workbench_purge_login", purge)),
            ("clickhouse-password", clickhouse),
        ]:
            save(RUNTIME / "worker" / name, value)
        save(
            RUNTIME / "bootstrap" / "settings",
            json.dumps(
                {
                    "adminDsn": dsn("feedback_intelligence", admin),
                    "principals": [
                        ["workbench_api_login", api, "workbench_api"],
                        ["workbench_worker_login", worker, "workbench_worker"],
                        ["workbench_purge_login", purge, "workbench_purger"],
                    ],
                }
            ),
        )
        for directory in ("vault/keys", "vault/vault"):
            (RUNTIME / directory).mkdir(parents=True, exist_ok=True, mode=0o700)
    subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(environment),
            "-f",
            "compose.workbench.yaml",
            "up",
            "--detach",
            "--build",
            "--wait",
            "--wait-timeout",
            "120",
        ],
        cwd=ROOT,
        check=True,
    )
    print("Workbench: http://localhost:8081/#workbench")
    print(f"Owner unlock code: {RUNTIME / 'api' / 'owner-code'} (private local file; not logged)")


if __name__ == "__main__":
    main()
