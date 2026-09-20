"""Regression checks for public benchmark provenance and drift detection."""

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_public_benchmark as benchmark


class PublicBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative in [benchmark.EXPERIMENT, Path("README.md")] + [
            benchmark.REPORT_DIR / f"{stem}-vs-sol-ai-reference.json"
            for _, stem in benchmark.METHODS
        ]:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(benchmark.ROOT / relative, target)
        (self.root / "docs").mkdir()
        self.root_patch = patch.object(benchmark, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def change_report(self, stem, mutate):
        path = self.root / benchmark.REPORT_DIR / f"{stem}-vs-sol-ai-reference.json"
        report = json.loads(path.read_text())
        mutate(report)
        path.write_text(json.dumps(report))

    def test_rejects_mismatched_reference_inputs(self):
        self.change_report(
            "rules-1.0.0",
            lambda report: report["inputs"].update(labels_sha256="different"),
        )
        with self.assertRaisesRegex(ValueError, "same corpus"):
            benchmark.build()

    def test_rejects_changed_closed_experiment_report(self):
        self.change_report(
            "gpt-5.4-mini-2026-03-17-partial",
            lambda report: report["summary"].update(primary_topic_accuracy=1),
        )
        with self.assertRaisesRegex(ValueError, "closed experiment disagree"):
            benchmark.build()

    def test_check_detects_readme_drift(self):
        with (
            patch("sys.argv", ["build_public_benchmark.py"]),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            benchmark.main()
        with (
            patch("sys.argv", ["build_public_benchmark.py", "--check"]),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            benchmark.main()
        path = self.root / "README.md"
        path.write_text(path.read_text().replace("88.12%", "100.00%"))
        with patch("sys.argv", ["build_public_benchmark.py", "--check"]):
            with self.assertRaisesRegex(
                SystemExit, "Stale generated content: README.md"
            ):
                benchmark.main()


if __name__ == "__main__":
    unittest.main()
