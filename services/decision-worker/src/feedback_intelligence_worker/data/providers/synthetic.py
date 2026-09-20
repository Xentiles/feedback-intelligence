"""Small committed zero-configuration dataset provider."""

from __future__ import annotations

import json
from pathlib import Path

from feedback_intelligence_worker.data.models import (
    CanonicalRecordError,
    DatasetLoadResult,
    DatasetMetadata,
    FeedbackRecord,
    ValidationReport,
)
from feedback_intelligence_worker.data.support import (
    ReportBuilder,
    checksum_files,
    metadata_for_records,
)


class SyntheticDatasetProvider:
    provider_id = "synthetic"

    def __init__(self, source_path: Path) -> None:
        self._source_path = source_path
        self._cached: DatasetLoadResult | None = None

    def metadata(self) -> DatasetMetadata:
        return self.load_feedback().metadata

    def validate_source(self) -> ValidationReport:
        return self.load_feedback().validation

    def load_feedback(self) -> DatasetLoadResult:
        if self._cached is None:
            self._cached = self._load()
        return self._cached

    def _load(self) -> DatasetLoadResult:
        report = ReportBuilder()
        records: list[FeedbackRecord] = []
        seen_ids: set[str] = set()
        empty_checksum = "0" * 64

        if not self._source_path.is_file():
            report.error(
                "source_not_found",
                f"Synthetic source file does not exist: {self._source_path}",
                source_file=str(self._source_path),
                blocking=True,
            )
            return DatasetLoadResult(
                records=(),
                metadata=metadata_for_records(
                    provider_id=self.provider_id,
                    dataset_name="Feedback Intelligence synthetic demo",
                    dataset_version="demo-data/0.1.0",
                    source_uri="repository:data/demo/feedback.jsonl",
                    license_name="CC BY 4.0",
                    attribution="Feedback Intelligence contributors",
                    default_language=None,
                    checksum_sha256=empty_checksum,
                    records=(),
                ),
                validation=report.freeze(),
            )

        checksum = checksum_files([self._source_path], relative_to=self._source_path.parent)
        try:
            lines = self._source_path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError as error:
            report.error(
                "unexpected_encoding",
                f"Synthetic JSONL must be UTF-8: {error}",
                source_file=self._source_path.name,
                blocking=True,
            )
            lines = []

        for row_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            report.records_discovered += 1
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise CanonicalRecordError("JSONL row must be an object")
                record = FeedbackRecord.from_dict(payload)
                if record.source.provider_id != self.provider_id:
                    raise CanonicalRecordError("source.provider_id must be synthetic")
                if record.source.source_record_id in seen_ids:
                    report.duplicate_records += 1
                    raise CanonicalRecordError("duplicate source_record_id")
            except (json.JSONDecodeError, KeyError, TypeError, CanonicalRecordError) as error:
                report.rejected_records += 1
                report.error(
                    "invalid_record",
                    str(error),
                    source_file=self._source_path.name,
                    row_number=row_number,
                )
                continue
            seen_ids.add(record.source.source_record_id)
            records.append(record)
            report.valid_records += 1

        if report.records_discovered == 0:
            report.error(
                "empty_dataset",
                "Synthetic dataset contains no records",
                source_file=self._source_path.name,
                blocking=True,
            )

        frozen_records = tuple(records)
        version = records[0].source.dataset_version if records else "demo-data/0.1.0"
        dataset_name = (
            records[0].source.dataset_name if records else "Feedback Intelligence synthetic demo"
        )
        return DatasetLoadResult(
            records=frozen_records,
            metadata=metadata_for_records(
                provider_id=self.provider_id,
                dataset_name=dataset_name,
                dataset_version=version,
                source_uri=f"file:{self._source_path}",
                license_name="CC BY 4.0",
                attribution="Feedback Intelligence contributors",
                default_language=None,
                checksum_sha256=checksum,
                records=frozen_records,
            ),
            validation=report.freeze(),
        )
