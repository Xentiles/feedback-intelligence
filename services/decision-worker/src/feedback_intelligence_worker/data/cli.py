"""Developer CLI for fetching, validating, profiling, and importing datasets."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from feedback_intelligence_worker.data.config import (
    SUPPORTED_PROVIDERS,
    build_provider,
    find_repository_root,
    selected_provider,
)
from feedback_intelligence_worker.data.fetch import DatasetFetchError, fetch_olist
from feedback_intelligence_worker.data.models import DatasetLoadResult, JsonValue
from feedback_intelligence_worker.data.profile import DatasetProfile, profile_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feedback-data",
        description="Normalize replaceable feedback datasets into the canonical contract.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Acquire an external dataset")
    fetch_parser.add_argument("provider", choices=("olist",))
    fetch_parser.add_argument("--destination", type=Path)
    fetch_parser.add_argument("--force", action="store_true")
    fetch_parser.set_defaults(handler=_command_fetch)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect a CSV before mapping it")
    inspect_parser.add_argument("file", type=Path)
    inspect_parser.add_argument("--sample", type=int, default=3)
    inspect_parser.set_defaults(handler=_command_inspect)

    for command, help_text, handler in (
        ("validate", "Validate source data and relationships", _command_validate),
        ("profile", "Profile canonical records without AI calls", _command_profile),
        ("import", "Write canonical JSONL and provenance sidecars", _command_import),
    ):
        command_parser = subparsers.add_parser(command, help=help_text)
        _add_provider_arguments(command_parser)
        command_parser.add_argument("--json", action="store_true", dest="as_json")
        if command == "validate":
            command_parser.add_argument("--show-issues", type=int, default=20)
        if command == "import":
            command_parser.add_argument("--output", type=Path)
        command_parser.set_defaults(handler=handler)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        return int(arguments.handler(arguments))
    except (DatasetFetchError, ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _add_provider_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "provider",
        nargs="?",
        choices=SUPPORTED_PROVIDERS,
        help="Defaults to FEEDBACK_DATA_PROVIDER or synthetic",
    )
    parser.add_argument("--path", type=Path, help="Synthetic JSONL or Olist raw directory")
    parser.add_argument("--file", type=Path, help="User CSV for the csv provider")
    parser.add_argument("--mapping", type=Path, help="Versioned YAML mapping for the csv provider")


def _load(arguments: argparse.Namespace) -> DatasetLoadResult:
    provider_name = selected_provider(arguments.provider)
    provider = build_provider(
        provider_name,
        path=arguments.path,
        file=arguments.file,
        mapping=arguments.mapping,
    )
    return provider.load_feedback()


def _command_fetch(arguments: argparse.Namespace) -> int:
    destination = arguments.destination or (find_repository_root() / "data/external/olist/raw")
    downloaded = fetch_olist(destination, force=arguments.force)
    print(f"Downloaded {arguments.provider} to {downloaded}")
    print("Run `feedback-data validate olist` before importing.")
    return 0


def _command_validate(arguments: argparse.Namespace) -> int:
    result = _load(arguments)
    if arguments.as_json:
        print(json.dumps(result.validation.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_validation(result, show_issues=arguments.show_issues)
    return 0 if result.validation.is_usable else 1


def _command_profile(arguments: argparse.Namespace) -> int:
    result = _load(arguments)
    profile = profile_dataset(result)
    if arguments.as_json:
        print(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_profile(profile)
    return 0 if result.validation.is_usable else 1


def _command_import(arguments: argparse.Namespace) -> int:
    result = _load(arguments)
    if not result.validation.is_usable:
        _print_validation(result, show_issues=20)
        print("Import stopped because the source has blocking validation errors.", file=sys.stderr)
        return 1
    provider_name = selected_provider(arguments.provider)
    output = arguments.output or (
        find_repository_root() / f"data/processed/{provider_name}/feedback.jsonl"
    )
    _write_import(result, output)
    if arguments.as_json:
        payload: dict[str, JsonValue] = {
            "output": str(output),
            "records_written": len(result.records),
            "metadata": result.metadata.mark_imported().to_dict(),
            "validation": result.validation.to_dict(),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_validation(result, show_issues=10)
        print(f"Canonical records written: {output}")
        print(f"Metadata written:          {output.with_suffix('.metadata.json')}")
        print(f"Validation written:        {output.with_suffix('.validation.json')}")
    return 0


def _command_inspect(arguments: argparse.Namespace) -> int:
    path: Path = arguments.file
    if not path.is_file():
        raise ValueError(f"CSV file does not exist: {path}")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            headers = reader.fieldnames or []
            rows: list[dict[str, str | None]] = []
            count = 0
            for row in reader:
                count += 1
                if len(rows) < max(arguments.sample, 0):
                    rows.append({key: value for key, value in row.items()})
    except UnicodeDecodeError as error:
        raise ValueError(f"CSV must be UTF-8: {error}") from error
    print(f"CSV: {path}")
    print(f"Columns ({len(headers)}): {', '.join(headers) if headers else '<none>'}")
    print(f"Rows: {count}")
    if rows:
        print("Sample (values may contain sensitive source data):")
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    print("Inspection does not import, redact, or call an AI model.")
    return 0


def _write_import(result: DatasetLoadResult, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    metadata_path = output.with_suffix(".metadata.json")
    validation_path = output.with_suffix(".validation.json")
    imported_metadata = result.metadata.mark_imported()
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as destination:
            for record in result.records:
                destination.write(
                    json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
                )
        temporary.replace(output)
        metadata_path.write_text(
            json.dumps(imported_metadata.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        validation_path.write_text(
            json.dumps(result.validation.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    finally:
        temporary.unlink(missing_ok=True)


def _print_validation(result: DatasetLoadResult, *, show_issues: int) -> None:
    report = result.validation
    print("Dataset validation")
    print(f"Provider:           {result.metadata.provider_id}")
    print(f"Records discovered: {report.records_discovered:,}")
    print(f"Valid:              {report.valid_records:,}")
    print(f"Warnings:           {report.warning_count:,}")
    print(f"Rejected:           {report.rejected_records:,}")
    print(f"Duplicates:         {report.duplicate_records:,}")
    print(f"Usable:             {'yes' if report.is_usable else 'no'}")
    visible = report.issues[: max(show_issues, 0)]
    if visible:
        print("Issues:")
        for issue in visible:
            location = ":".join(
                part
                for part in (
                    issue.source_file,
                    None if issue.row_number is None else str(issue.row_number),
                )
                if part is not None
            )
            suffix = f" ({location})" if location else ""
            print(f"  [{issue.severity.value}] {issue.code}: {issue.message}{suffix}")
    hidden = len(report.issues) - len(visible)
    if hidden > 0:
        print(f"  … {hidden:,} additional issue(s); use --json for the complete report")


def _print_profile(profile: DatasetProfile) -> None:
    print("Dataset profile")
    print(f"Record count:       {profile.record_count:,}")
    print(f"Date range:         {profile.date_start or '<none>'} → {profile.date_end or '<none>'}")
    print(f"Missing text:       {profile.missing_text_percentage:.3f}% of discovered rows")
    print(f"Products:           {profile.product_count:,}")
    print(f"Categories:         {profile.category_count:,}")
    print(f"Duplicates:         {profile.duplicate_count:,}")
    print(f"Rejected:           {profile.rejected_count:,}")
    print(f"Ratings:            {json.dumps(profile.rating_distribution, sort_keys=True)}")
    print(f"Languages:          {json.dumps(profile.language_distribution, sort_keys=True)}")
    print(f"Reviews per month:  {json.dumps(profile.reviews_per_month, sort_keys=True)}")


if __name__ == "__main__":
    raise SystemExit(main())
