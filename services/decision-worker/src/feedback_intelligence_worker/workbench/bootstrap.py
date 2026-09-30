"""Apply forward migrations and install separate local service principals."""

from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
from psycopg import sql

from feedback_intelligence_worker.storage.repository import StorageRepository


def main() -> None:
    path = Path(os.environ["WORKBENCH_BOOTSTRAP_FILE"])
    settings = json.loads(path.read_text())
    with StorageRepository(settings["adminDsn"]) as repository:
        for migration in sorted(Path("/app/infra/postgres/migrations").glob("*.sql")):
            repository.apply_migration(migration)
    with psycopg.connect(settings["adminDsn"], autocommit=True) as db:
        for name, password, capability in settings["principals"]:
            if db.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (name,)).fetchone() is None:
                db.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(name), sql.Literal(password)
                    )
                )
            db.execute(
                sql.SQL("GRANT {} TO {}").format(sql.Identifier(capability), sql.Identifier(name))
            )
    print("Workbench migrations and service principals ready")


if __name__ == "__main__":
    main()
