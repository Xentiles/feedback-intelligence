# /// script
# requires-python = ">=3.13"
# dependencies = ["jsonschema==4.26.0"]
# ///
"""Validate foundation metadata and JSON Schema documents, without live providers."""

import argparse
import hashlib
import json
import subprocess
import tomllib
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.validators import validator_for
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
INTERNAL_PLAN_DIRECTORY = "Project Plan Documentation"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic-manifest", type=Path)
    parser.add_argument("--decision-jsonl", type=Path)
    parser.add_argument("--decision-fixture", type=Path)
    arguments = parser.parse_args()
    _validate_publication_boundary()
    schema_paths = sorted(
        path
        for directory in (ROOT / "schemas", ROOT / "contracts")
        for path in directory.rglob("*.schema.json")
    )
    for path in schema_paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(schema, dict) or "$schema" not in schema:
            raise ValueError(
                f"{path.relative_to(ROOT)} must declare a JSON Schema dialect"
            )
        schema_validator = validator_for(schema, default=None)
        if schema_validator is None:
            raise ValueError(f"Unsupported JSON Schema dialect: {schema['$schema']}")
        schema_validator.check_schema(schema)

    decision_manifest_schema = json.loads(
        (ROOT / "schemas/feedback-decision/manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(decision_manifest_schema)
    manifests = sorted((ROOT / "schemas/feedback-decision").glob("*/manifest.json"))
    if not manifests:
        raise ValueError("No decision-schema manifest found")
    for path in manifests:
        metadata = json.loads(path.read_text(encoding="utf-8"))
        validator.validate(metadata)
        if metadata["version"] != path.parent.name:
            raise ValueError(
                f"Version does not match directory: {path.relative_to(ROOT)}"
            )
        _validate_decision_manifest_semantics(metadata, path)

    policy_manifest_schema = json.loads(
        (ROOT / "schemas/aggregation-policy/manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )
    policy_validator = Draft202012Validator(policy_manifest_schema)
    policy_manifests = sorted(
        (ROOT / "schemas/aggregation-policy").glob("*/manifest.json")
    )
    if not policy_manifests:
        raise ValueError("No aggregation-policy manifest found")
    decision_manifest_path = ROOT / "schemas/feedback-decision/1.0.0/manifest.json"
    decision_sha256 = (
        f"sha256:{hashlib.sha256(decision_manifest_path.read_bytes()).hexdigest()}"
    )
    for path in policy_manifests:
        metadata = json.loads(path.read_text(encoding="utf-8"))
        policy_validator.validate(metadata)
        if metadata["version"] != path.parent.name:
            raise ValueError(
                f"Policy version does not match directory: {path.relative_to(ROOT)}"
            )
        if metadata["decision_schema"]["sha256"] != decision_sha256:
            raise ValueError(
                f"Policy decision-schema checksum is stale: {path.relative_to(ROOT)}"
            )
        question_ids = [question["id"] for question in metadata["questions"]]
        decision_metadata = json.loads(decision_manifest_path.read_text())
        decision_ids = [question["id"] for question in decision_metadata["questions"]]
        if question_ids != decision_ids:
            relative_path = path.relative_to(ROOT)
            raise ValueError(
                f"Policy questions do not match decision schema: {relative_path}"
            )
        if metadata["status"] == "awaiting_calibration" and any(
            question["thresholds"] is not None for question in metadata["questions"]
        ):
            raise ValueError("Awaiting-calibration policy cannot contain thresholds")

    feedback_schema = json.loads(
        (ROOT / "contracts/data/feedback-record.schema.json").read_text(
            encoding="utf-8"
        )
    )
    feedback_validator = Draft202012Validator(feedback_schema)
    demo_path = ROOT / "data/demo/feedback.jsonl"
    demo_records = 0
    for line_number, line in enumerate(
        demo_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            feedback_validator.validate(json.loads(line))
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError(
                f"Invalid demo record at {demo_path}:{line_number}: {error}"
            ) from error
        demo_records += 1
    if demo_records == 0:
        raise ValueError("The committed demo dataset is empty")

    evaluation_dir = ROOT / "evaluation/datasets/feedback-decision-1.0.0"
    selection_manifest = json.loads(
        (evaluation_dir / "selection-manifest.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(
        json.loads(
            (ROOT / "contracts/evaluation/selection-manifest.schema.json").read_text()
        )
    ).validate(selection_manifest)
    evaluation_counts: dict[str, int] = {}
    for name, schema_name in (
        ("records", "evaluation-sample-record.schema.json"),
        ("labels", "annotation-record.schema.json"),
    ):
        content = (evaluation_dir / f"{name}.jsonl").read_bytes()
        validator = Draft202012Validator(
            json.loads((ROOT / "contracts/evaluation" / schema_name).read_text())
        )
        rows = [json.loads(line) for line in content.splitlines() if line.strip()]
        for row in rows:
            validator.validate(row)
        evaluation_counts[name] = len(rows)
        checksum_key = (
            "records_sha256" if name == "records" else "labels_template_sha256"
        )
        if hashlib.sha256(content).hexdigest() != selection_manifest[checksum_key]:
            raise ValueError(
                f"Evaluation {name} checksum differs from selection manifest"
            )
    if evaluation_counts != {"records": 480, "labels": 480}:
        raise ValueError(f"Evaluation corpus counts are invalid: {evaluation_counts}")

    readiness_path = ROOT / "evaluation/reports/feedback-decision-1.0.0/readiness.json"
    readiness_report = json.loads(readiness_path.read_text(encoding="utf-8"))
    readiness_schema = json.loads(
        (
            ROOT / "contracts/evaluation/evaluation-readiness-report.schema.json"
        ).read_text()
    )
    Draft202012Validator(readiness_schema).validate(readiness_report)
    expected_readiness_inputs = {
        "records_sha256": selection_manifest["records_sha256"],
        "labels_sha256": selection_manifest["labels_template_sha256"],
        "decision_schema_sha256": decision_sha256,
    }
    if readiness_report["inputs"] != expected_readiness_inputs:
        raise ValueError("Evaluation readiness report input checksums are stale")
    if readiness_report["readiness"]["total"] != 480:
        raise ValueError("Evaluation readiness report record count is invalid")

    ai_dir = ROOT / "evaluation/ai-reference/feedback-decision-1.0.0"
    ai_manifest = json.loads((ai_dir / "manifest.json").read_text(encoding="utf-8"))
    ai_manifest_schema = json.loads(
        (ROOT / "contracts/evaluation/ai-reference-manifest.schema.json").read_text()
    )
    Draft202012Validator(ai_manifest_schema).validate(ai_manifest)
    ai_records = (ai_dir / "records.jsonl").read_bytes()
    ai_labels = (ai_dir / "labels.jsonl").read_bytes()
    if ai_records != (evaluation_dir / "records.jsonl").read_bytes():
        raise ValueError(
            "AI-reference records must exactly match the frozen evaluation sample"
        )
    if hashlib.sha256(ai_records).hexdigest() != ai_manifest["records_sha256"]:
        raise ValueError("AI-reference record checksum is stale")
    if hashlib.sha256(ai_labels).hexdigest() != ai_manifest["labels_sha256"]:
        raise ValueError("AI-reference label checksum is stale")
    annotation_validator = Draft202012Validator(
        json.loads(
            (ROOT / "contracts/evaluation/annotation-record.schema.json").read_text()
        )
    )
    ai_label_rows = [
        json.loads(line) for line in ai_labels.splitlines() if line.strip()
    ]
    for row in ai_label_rows:
        annotation_validator.validate(row)
    if len(ai_label_rows) != 480:
        raise ValueError("AI-reference labels must cover all 480 records")

    prediction_validator = Draft202012Validator(
        json.loads(
            (
                ROOT / "contracts/evaluation/evaluation-prediction.schema.json"
            ).read_text()
        )
    )
    score_validator = Draft202012Validator(
        json.loads(
            (ROOT / "contracts/evaluation/evaluation-report.schema.json").read_text()
        )
    )
    benchmark_files = {
        "SemIf": (
            "semif-qwen3.5-4b-mlx-q4-851bf6e8.predictions.jsonl",
            "semif-qwen3.5-4b-mlx-q4-851bf6e8-vs-sol-ai-reference.json",
        ),
        "rules": (
            "rules-1.0.0.predictions.jsonl",
            "rules-1.0.0-vs-sol-ai-reference.json",
        ),
    }
    for engine_name, (prediction_name, report_name) in benchmark_files.items():
        prediction_path = (
            ROOT / "evaluation/benchmarks/feedback-decision-1.0.0" / prediction_name
        )
        prediction_bytes = prediction_path.read_bytes()
        prediction_rows = [
            json.loads(line) for line in prediction_bytes.splitlines() if line.strip()
        ]
        for row in prediction_rows:
            prediction_validator.validate(row)
        if len(prediction_rows) != 480 or any(
            row["status"] != "success" for row in prediction_rows
        ):
            raise ValueError(
                f"Committed {engine_name} benchmark must contain 480 successful predictions"
            )

        score_path = ROOT / "evaluation/reports/feedback-decision-1.0.0" / report_name
        score_report = json.loads(score_path.read_text(encoding="utf-8"))
        score_validator.validate(score_report)
        expected_score_inputs = {
            "records_sha256": ai_manifest["records_sha256"],
            "labels_sha256": ai_manifest["labels_sha256"],
            "predictions_sha256": hashlib.sha256(prediction_bytes).hexdigest(),
            "decision_schema_sha256": decision_sha256,
        }
        if score_report["inputs"] != expected_score_inputs:
            raise ValueError(f"{engine_name} score report input checksums are stale")
        report_hash = score_report.pop("report_sha256")
        canonical_report = json.dumps(
            score_report, sort_keys=True, separators=(",", ":")
        ).encode()
        if hashlib.sha256(canonical_report).hexdigest() != report_hash:
            raise ValueError(f"{engine_name} score report hash is invalid")

    llm_prediction_path = (
        ROOT
        / "evaluation/benchmarks/feedback-decision-1.0.0"
        / "gpt-5.4-mini-2026-03-17.predictions.jsonl"
    )
    llm_prediction_bytes = llm_prediction_path.read_bytes()
    llm_prediction_rows = [
        json.loads(line) for line in llm_prediction_bytes.splitlines() if line.strip()
    ]
    for row in llm_prediction_rows:
        prediction_validator.validate(row)
    if len(llm_prediction_rows) != 192 or any(
        row["status"] != "success" for row in llm_prediction_rows
    ):
        raise ValueError(
            "Committed LLM experiment must contain 192 successful predictions"
        )
    ai_record_ids = {
        json.loads(line)["feedback_id"]
        for line in ai_records.splitlines()
        if line.strip()
    }
    llm_prediction_ids = {row["feedback_id"] for row in llm_prediction_rows}
    if len(llm_prediction_ids) != 192 or not llm_prediction_ids <= ai_record_ids:
        raise ValueError(
            "LLM prediction ids must be a unique subset of the AI-reference corpus"
        )

    llm_report_path = (
        ROOT
        / "evaluation/reports/feedback-decision-1.0.0"
        / "gpt-5.4-mini-2026-03-17-partial-vs-sol-ai-reference.json"
    )
    llm_report_bytes = llm_report_path.read_bytes()
    llm_report = json.loads(llm_report_bytes)
    score_validator.validate(llm_report)
    if llm_report.get("partial_evaluation") is not True:
        raise ValueError("LLM score report must remain explicitly partial")
    if llm_report["summary"].get("record_count") != 192:
        raise ValueError("LLM score report record count is invalid")
    if llm_report["summary"].get("target_record_count") != 480:
        raise ValueError("LLM score report target count is invalid")
    expected_llm_inputs = {
        "records_sha256": ai_manifest["records_sha256"],
        "labels_sha256": ai_manifest["labels_sha256"],
        "predictions_sha256": hashlib.sha256(llm_prediction_bytes).hexdigest(),
        "decision_schema_sha256": decision_sha256,
    }
    if llm_report["inputs"] != expected_llm_inputs:
        raise ValueError("LLM score report input checksums are stale")
    llm_report_hash = llm_report.pop("report_sha256")
    canonical_llm_report = json.dumps(
        llm_report, sort_keys=True, separators=(",", ":")
    ).encode()
    if hashlib.sha256(canonical_llm_report).hexdigest() != llm_report_hash:
        raise ValueError("LLM score report hash is invalid")

    experiment_path = llm_prediction_path.with_name(
        "gpt-5.4-mini-2026-03-17.experiment.json"
    )
    experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
    experiment_validator = Draft202012Validator(
        json.loads(
            (ROOT / "contracts/evaluation/llm-experiment.schema.json").read_text()
        )
    )
    experiment_validator.validate(experiment)
    if (
        experiment["artifacts"]["predictions_sha256"]
        != hashlib.sha256(llm_prediction_bytes).hexdigest()
    ):
        raise ValueError("LLM experiment prediction checksum is stale")
    if (
        experiment["artifacts"]["report_sha256"]
        != hashlib.sha256(llm_report_bytes).hexdigest()
    ):
        raise ValueError("LLM experiment report checksum is stale")

    extra_counts: list[str] = []
    if arguments.synthetic_manifest is not None:
        manifest_schema = json.loads(
            (ROOT / "contracts/data/synthetic-seed-manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )
        manifest = json.loads(arguments.synthetic_manifest.read_text(encoding="utf-8"))
        Draft202012Validator(manifest_schema).validate(manifest)
        extra_counts.append("1 generated seed manifest")

    envelope_schema = json.loads(
        (ROOT / "contracts/decisions/decision-envelope.schema.json").read_text(
            encoding="utf-8"
        )
    )
    if arguments.decision_jsonl is not None:
        envelope_validator = Draft202012Validator(envelope_schema)
        decision_count = 0
        for line in arguments.decision_jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                envelope_validator.validate(json.loads(line))
                decision_count += 1
        if decision_count == 0:
            raise ValueError("Decision JSONL is empty")
        extra_counts.append(f"{decision_count} decision envelope(s)")
    if arguments.decision_fixture is not None:
        fixture_schema = json.loads(
            (ROOT / "contracts/decisions/decision-fixture-set.schema.json").read_text(
                encoding="utf-8"
            )
        )
        registry = Registry().with_resource(
            envelope_schema["$id"], Resource.from_contents(envelope_schema)
        )
        fixture_validator = Draft202012Validator(fixture_schema, registry=registry)
        fixture_validator.validate(
            json.loads(arguments.decision_fixture.read_text(encoding="utf-8"))
        )
        extra_counts.append("1 decision fixture set")

    counts = [
        f"{len(schema_paths)} JSON Schema document(s)",
        f"{len(manifests)} decision manifest(s)",
        f"{len(policy_manifests)} policy manifest(s)",
        f"{demo_records} demo record(s)",
        "480 evaluation record(s)",
        *extra_counts,
        "1 evaluation readiness report",
        "1 AI-reference corpus",
        "1,152 benchmark predictions across SemIf, rules, and LLM",
        "3 AI-reference score reports",
        "1 closed LLM experiment record",
    ]
    print(f"Validated {', '.join(counts)}.")
    print("Decision questions are structurally and semantically validated.")


def _validate_publication_boundary() -> None:
    required_files = (
        ROOT / "LICENSE",
        ROOT / "LICENSE-SCOPE.md",
        ROOT / "LICENSES/CC-BY-4.0.txt",
        ROOT / "NOTICE",
        ROOT / "THIRD_PARTY_NOTICES.md",
    )
    missing = [str(path.relative_to(ROOT)) for path in required_files if not path.is_file()]
    if missing:
        raise ValueError(f"Missing repository license files: {', '.join(missing)}")

    apache_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    if "Apache License" not in apache_text or "Version 2.0, January 2004" not in apache_text:
        raise ValueError("Root LICENSE is not the Apache License 2.0 text")
    worker_license = (ROOT / "services/decision-worker/LICENSE").read_text(encoding="utf-8")
    if worker_license.rstrip() != apache_text.rstrip():
        raise ValueError("Worker package Apache license copy differs from root LICENSE")
    root_notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    worker_notice = (ROOT / "services/decision-worker/NOTICE").read_text(encoding="utf-8")
    if worker_notice.rstrip() != root_notice.rstrip():
        raise ValueError("Worker package NOTICE copy differs from root NOTICE")

    cc_text = (ROOT / "LICENSES/CC-BY-4.0.txt").read_text(encoding="utf-8")
    if "Creative Commons Attribution 4.0 International Public License" not in cc_text:
        raise ValueError("CC BY 4.0 legal code is missing or unrecognized")

    web_package = json.loads((ROOT / "apps/web/package.json").read_text(encoding="utf-8"))
    if web_package.get("license") != "Apache-2.0":
        raise ValueError("Web package must declare Apache-2.0")

    worker_project = tomllib.loads(
        (ROOT / "services/decision-worker/pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    if worker_project.get("license") != "Apache-2.0":
        raise ValueError("Worker package must declare Apache-2.0")
    if worker_project.get("license-files") != ["LICENSE", "NOTICE"]:
        raise ValueError("Worker package must include the Apache license and NOTICE")

    api_project = ElementTree.parse(
        ROOT / "services/api/src/FeedbackIntelligence.Api/FeedbackIntelligence.Api.csproj"
    )
    license_expression = api_project.findtext(".//PackageLicenseExpression")
    if license_expression != "Apache-2.0":
        raise ValueError("API project must declare Apache-2.0")

    expected_ignore = f"/{INTERNAL_PLAN_DIRECTORY}/"
    gitignore_lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    if expected_ignore not in gitignore_lines:
        raise ValueError("Internal planning directory must remain Git-ignored")
    dockerignore_lines = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    if INTERNAL_PLAN_DIRECTORY not in dockerignore_lines:
        raise ValueError("Internal planning directory must remain outside Docker contexts")

    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8").split("\0")
    prefix = f"{INTERNAL_PLAN_DIRECTORY}/"
    leaked = [path for path in tracked if path.startswith(prefix)]
    if leaked:
        raise ValueError(
            "Internal planning material is tracked for publication: " + ", ".join(leaked)
        )

    removed_provider_artifacts = (
        ROOT / "data/fixtures/decisions/demo-jev-1.13.0.json",
        ROOT
        / "evaluation/benchmarks/feedback-decision-1.0.0/jev-1.13.0.predictions.jsonl",
        ROOT
        / "evaluation/reports/feedback-decision-1.0.0/jev-1.13.0-vs-sol-ai-reference.json",
        ROOT
        / "evaluation/reports/feedback-decision-1.0.0/jev-1.13.0-vs-sol-ai-reference.md",
        ROOT
        / "services/api/src/FeedbackIntelligence.Api/Fixtures/dashboard-demo-jev.json",
        ROOT
        / "services/decision-worker/src/feedback_intelligence_worker/decision/jev.py",
    )
    retained = [
        str(path.relative_to(ROOT)) for path in removed_provider_artifacts if path.exists()
    ]
    if retained:
        raise ValueError(
            "Provider-restricted benchmark material returned to the publication set: "
            + ", ".join(retained)
        )


def _validate_decision_manifest_semantics(metadata: dict, path: Path) -> None:
    questions = metadata["questions"]
    question_ids = [question["id"] for question in questions]
    if len(question_ids) != len(set(question_ids)):
        raise ValueError(f"Duplicate question id in {path.relative_to(ROOT)}")
    for question in questions:
        if question["primitive"] == "choice":
            option_ids = [option["id"] for option in question["options"]]
            if len(option_ids) != len(set(option_ids)):
                raise ValueError(f"Duplicate option in question {question['id']}")
        elif question["primitive"] == "score":
            values = [level["value"] for level in question["levels"]]
            labels = [level["label"] for level in question["levels"]]
            if values != list(range(len(values))):
                raise ValueError(
                    f"Score levels must be consecutive in {question['id']}"
                )
            if len(labels) != len(set(labels)):
                raise ValueError(f"Duplicate score label in question {question['id']}")


if __name__ == "__main__":
    main()
