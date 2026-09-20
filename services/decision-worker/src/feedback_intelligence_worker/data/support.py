"""Shared deterministic helpers for dataset adapters."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from feedback_intelligence_worker.data.models import (
    DatasetMetadata,
    DateRange,
    FeedbackRecord,
    IssueSeverity,
    ValidationIssue,
    ValidationReport,
)


@dataclass(slots=True)
class ReportBuilder:
    records_discovered: int = 0
    valid_records: int = 0
    rejected_records: int = 0
    duplicate_records: int = 0
    missing_text_records: int = 0
    issues: list[ValidationIssue] = field(default_factory=list)

    def warning(
        self,
        code: str,
        message: str,
        *,
        source_record_id: str | None = None,
        source_file: str | None = None,
        row_number: int | None = None,
    ) -> None:
        self.issues.append(
            ValidationIssue(
                code=code,
                message=message,
                severity=IssueSeverity.WARNING,
                source_record_id=source_record_id,
                source_file=source_file,
                row_number=row_number,
            )
        )

    def error(
        self,
        code: str,
        message: str,
        *,
        source_record_id: str | None = None,
        source_file: str | None = None,
        row_number: int | None = None,
        blocking: bool = False,
    ) -> None:
        self.issues.append(
            ValidationIssue(
                code=code,
                message=message,
                severity=IssueSeverity.ERROR,
                source_record_id=source_record_id,
                source_file=source_file,
                row_number=row_number,
                blocking=blocking,
            )
        )

    def freeze(self) -> ValidationReport:
        return ValidationReport(
            records_discovered=self.records_discovered,
            valid_records=self.valid_records,
            rejected_records=self.rejected_records,
            duplicate_records=self.duplicate_records,
            missing_text_records=self.missing_text_records,
            issues=tuple(self.issues),
        )


def checksum_files(paths: list[Path], *, relative_to: Path) -> str:
    """Hash file identity and content in a stable order."""
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item.relative_to(relative_to))):
        relative_name = str(path.relative_to(relative_to)).encode()
        digest.update(len(relative_name).to_bytes(8, "big"))
        digest.update(relative_name)
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def metadata_for_records(
    *,
    provider_id: str,
    dataset_name: str,
    dataset_version: str,
    source_uri: str,
    license_name: str,
    attribution: str,
    default_language: str | None,
    checksum_sha256: str,
    records: tuple[FeedbackRecord, ...],
) -> DatasetMetadata:
    dates = [record.occurred_at for record in records]
    date_range = None if not dates else DateRange(start=min(dates), end=max(dates))
    return DatasetMetadata(
        provider_id=provider_id,
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        source_uri=source_uri,
        license=license_name,
        attribution=attribution,
        default_language=default_language,
        record_count=len(records),
        date_range=date_range,
        checksum_sha256=checksum_sha256,
    )
