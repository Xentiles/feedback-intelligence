"""Reproducibility and leakage tests for the versioned synthetic generator."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from _pytest.capture import CaptureFixture

from feedback_intelligence_worker.data.providers.synthetic import SyntheticDatasetProvider
from feedback_intelligence_worker.privacy import PrivacyBoundary
from feedback_intelligence_worker.synthetic.cli import main
from feedback_intelligence_worker.synthetic.generator import (
    GeneratedSyntheticDataset,
    SyntheticDatasetGenerator,
)
from feedback_intelligence_worker.synthetic.spec import GeneratorSpec, load_generator_spec


@pytest.fixture(scope="module")
def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def generator_spec(repository_root: Path) -> GeneratorSpec:
    return load_generator_spec(repository_root / "data/synthetic/generator-v1.yaml")


@pytest.fixture(scope="module")
def generated(generator_spec: GeneratorSpec) -> GeneratedSyntheticDataset:
    return SyntheticDatasetGenerator(generator_spec).generate()


def test_default_generation_covers_declared_scope(
    generator_spec: GeneratorSpec,
    generated: GeneratedSyntheticDataset,
) -> None:
    assert len(generated.records) == 10_000
    assert len(generated.provenance) == 10_000
    assert {item.source_type for item in generated.provenance} == {
        "product_review",
        "support_ticket",
        "delivery_survey",
        "return_feedback",
        "site_feedback",
    }
    assert {item.locale for item in generated.provenance} == {"en-GB", "sv-SE"}
    assert {item.scenario_id for item in generated.provenance} == {
        scenario.scenario_id for scenario in generator_spec.scenarios
    }
    assert {product for item in generated.provenance for product in item.product_ids} == {
        product.product_id for product in generator_spec.products
    }

    dates = [record.occurred_at.date() for record in generated.records]
    assert min(dates) == generator_spec.start_date
    assert max(dates) == generator_spec.start_date + timedelta(days=generator_spec.day_count - 1)
    assert generated.manifest["record_count"] == 10_000
    assert generated.manifest["config_sha256"] == generator_spec.checksum_sha256
    assert all(event["affected_records"] > 0 for event in generated.manifest["events"])


def test_planted_events_stay_within_their_declared_windows(
    generator_spec: GeneratorSpec,
    generated: GeneratedSyntheticDataset,
) -> None:
    records_by_id = {record.feedback_id: record for record in generated.records}
    events = {event.event_id: event for event in generator_spec.events}
    for item in generated.provenance:
        if item.synthetic_event_id is None:
            continue
        event = events[item.synthetic_event_id]
        record_date = records_by_id[item.feedback_id].occurred_at.date()
        day_offset = (record_date - generator_spec.start_date).days
        assert event.active_on(day_offset)
        assert item.scenario_id == event.scenario_id
        if event.product_id is not None:
            assert item.product_ids[0] == event.product_id


def test_provenance_is_excluded_from_records_and_model_state(
    generated: GeneratedSyntheticDataset,
) -> None:
    prohibited = {"scenario_id", "synthetic_event_id", "generator_expectations"}
    for record in generated.records:
        assert prohibited.isdisjoint(record.to_dict())
        assert prohibited.isdisjoint(record.metadata)

    prepared = PrivacyBoundary().prepare_for_decision(generated.records[0])
    serialized = json.dumps(prepared.to_decision_state())
    assert all(field not in serialized for field in prohibited)
    assert generated.provenance[0].scenario_id not in serialized


def test_same_seed_is_byte_identical_and_another_seed_differs(
    generator_spec: GeneratorSpec,
) -> None:
    generator = SyntheticDatasetGenerator(generator_spec)
    first = generator.generate(seed=42, record_count=250)
    second = generator.generate(seed=42, record_count=250)
    different = generator.generate(seed=43, record_count=250)

    assert first.feedback_bytes() == second.feedback_bytes()
    assert first.provenance_bytes() == second.provenance_bytes()
    assert first.manifest_bytes() == second.manifest_bytes()
    assert first.feedback_bytes() != different.feedback_bytes()


def test_cli_outputs_verify_and_load_as_canonical_records(
    generator_spec: GeneratorSpec,
    repository_root: Path,
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    spec_path = repository_root / "data/synthetic/generator-v1.yaml"
    output = tmp_path / "generated"
    assert (
        main(
            [
                "generate",
                "--spec",
                str(spec_path),
                "--output",
                str(output),
                "--seed",
                "8675309",
                "--count",
                "500",
                "--json",
            ]
        )
        == 0
    )
    generation_output = json.loads(capsys.readouterr().out)
    assert generation_output["record_count"] == 500
    assert generation_output["config_sha256"] == generator_spec.checksum_sha256

    assert main(["verify", "--spec", str(spec_path), "--output", str(output), "--json"]) == 0
    verification_output = json.loads(capsys.readouterr().out)
    assert verification_output["verified"] is True
    assert verification_output["mismatches"] == []

    result = SyntheticDatasetProvider(output / "feedback.jsonl").load_feedback()
    assert result.validation.is_usable
    assert result.validation.valid_records == 500
    assert result.validation.rejected_records == 0
    assert result.metadata.dataset_name == (
        "Feedback Intelligence deterministic synthetic retail feedback"
    )
    assert result.metadata.source_uri == f"file:{output / 'feedback.jsonl'}"


def test_verify_detects_output_tampering(
    repository_root: Path,
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    spec_path = repository_root / "data/synthetic/generator-v1.yaml"
    output = tmp_path / "generated"
    assert main(["generate", "--spec", str(spec_path), "--output", str(output)]) == 0
    capsys.readouterr()
    with (output / "feedback.jsonl").open("ab") as destination:
        destination.write(b"\n")

    assert main(["verify", "--spec", str(spec_path), "--output", str(output), "--json"]) == 1
    verification_output = json.loads(capsys.readouterr().out)
    assert verification_output["verified"] is False
    assert verification_output["mismatches"] == [
        "feedback.jsonl differs from deterministic regeneration"
    ]
