"""Dataset CLI tests use committed fixtures and make no network or AI calls."""

from __future__ import annotations

import json
from pathlib import Path

from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from feedback_intelligence_worker.data.cli import main
from feedback_intelligence_worker.data.config import selected_provider
from feedback_intelligence_worker.data.fetch import fetch_olist

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures"


def test_provider_selection_uses_environment_with_explicit_override(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("FEEDBACK_DATA_PROVIDER", "olist")

    assert selected_provider(None) == "olist"
    assert selected_provider("synthetic") == "synthetic"


def test_validate_and_profile_synthetic(capsys: CaptureFixture[str]) -> None:
    assert main(["validate", "synthetic"]) == 0
    assert main(["profile", "synthetic", "--json"]) == 0
    assert '"record_count": 9' in capsys.readouterr().out


def test_import_writes_canonical_records_and_sidecars(tmp_path: Path) -> None:
    output = tmp_path / "feedback.jsonl"

    exit_code = main(
        [
            "import",
            "olist",
            "--path",
            str(FIXTURES / "olist"),
            "--output",
            str(output),
            "--json",
        ]
    )

    assert exit_code == 0
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    metadata = json.loads(output.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    validation = json.loads(output.with_suffix(".validation.json").read_text(encoding="utf-8"))
    assert len(records) == 3
    assert all(record["privacy_status"] == "uninspected" for record in records)
    assert metadata["provider_id"] == "olist"
    assert metadata["imported_at"] is not None
    assert validation["rejected_records"] == 5


def test_inspect_csv_reports_shape(capsys: CaptureFixture[str]) -> None:
    assert main(["inspect", str(FIXTURES / "csv/customer-feedback.csv"), "--sample", "0"]) == 0
    assert "customer-feedback.csv" in capsys.readouterr().out


def test_fetch_olist_uses_explicit_output_directory(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_download(handle: str, *, output_dir: str, force_download: bool) -> str:
        captured.update(
            handle=handle,
            output_dir=output_dir,
            force_download=force_download,
        )
        return output_dir

    monkeypatch.setattr("kagglehub.dataset_download", fake_download)

    assert fetch_olist(tmp_path, force=True) == tmp_path
    assert captured == {
        "handle": "olistbr/brazilian-ecommerce",
        "output_dir": str(tmp_path),
        "force_download": True,
    }
