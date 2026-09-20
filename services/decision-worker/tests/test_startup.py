"""Startup checks for the decision-worker command."""

from __future__ import annotations

import subprocess
import sys

from feedback_intelligence_worker.cli import WORKER_STATUS


def test_module_starts_and_reports_worker_status() -> None:
    """The packaged module starts, reports its state, and exits cleanly."""
    result = subprocess.run(
        [sys.executable, "-m", "feedback_intelligence_worker"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == WORKER_STATUS
    assert result.stderr == ""
