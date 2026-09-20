"""Minimal mapping-driven provider for user-supplied CSV feedback."""

from __future__ import annotations

import csv
import hashlib
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from feedback_intelligence_worker.data.models import (
    CanonicalRecordError,
    DatasetLoadResult,
    DatasetMetadata,
    FeedbackRecord,
    Rating,
    RelatedProduct,
    SourceReference,
    ValidationReport,
    canonical_feedback_id,
)
from feedback_intelligence_worker.data.support import ReportBuilder, metadata_for_records


class MappedCsvDatasetProvider:
    """Map a flat CSV into Level A/B canonical feedback records."""

    provider_id = "csv"

    def __init__(self, source_path: Path, mapping_path: Path) -> None:
        self._source_path = source_path
        self._mapping_path = mapping_path
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
        checksum = self._checksum()
        mapping = self._read_mapping(report)
        dataset_name = str(mapping.get("dataset_name", self._source_path.stem))
        dataset_version = str(mapping.get("dataset_version", f"source-sha256:{checksum[:12]}"))
        language = _optional_text(mapping.get("language"))
        channel = _optional_text(mapping.get("channel"))
        license_name = str(mapping.get("license", "User supplied; permission not verified"))
        attribution = str(mapping.get("attribution", "User supplied data"))

        if any(issue.blocking for issue in report.issues):
            return self._result(
                (),
                report,
                checksum,
                dataset_name,
                dataset_version,
                language,
                license_name,
                attribution,
            )

        columns_value = mapping.get("columns")
        if not isinstance(columns_value, dict):
            report.error(
                "invalid_mapping",
                "Mapping must contain a 'columns' object",
                source_file=self._mapping_path.name,
                blocking=True,
            )
            return self._result(
                (),
                report,
                checksum,
                dataset_name,
                dataset_version,
                language,
                license_name,
                attribution,
            )
        columns = {str(key): str(value) for key, value in columns_value.items()}
        missing_mappings = [key for key in ("id", "text", "timestamp") if not columns.get(key)]
        if missing_mappings:
            report.error(
                "invalid_mapping",
                f"Mapping is missing required fields: {', '.join(missing_mappings)}",
                source_file=self._mapping_path.name,
                blocking=True,
            )
            return self._result(
                (),
                report,
                checksum,
                dataset_name,
                dataset_version,
                language,
                license_name,
                attribution,
            )

        time_zone = self._time_zone(mapping, report)
        rating_min, rating_max = self._rating_scale(mapping, report)
        rows = self._read_csv(set(columns.values()), report)
        if rows is None or any(issue.blocking for issue in report.issues):
            return self._result(
                (),
                report,
                checksum,
                dataset_name,
                dataset_version,
                language,
                license_name,
                attribution,
            )

        records: list[FeedbackRecord] = []
        seen_ids: set[str] = set()
        for row_number, row in rows:
            source_id = row.get(columns["id"], "").strip()
            if not source_id:
                self._reject(report, "missing_source_id", "Mapped id is blank", None, row_number)
                continue
            if source_id in seen_ids:
                report.duplicate_records += 1
                self._reject(
                    report,
                    "duplicate_source_record",
                    f"Duplicate mapped id: {source_id}",
                    source_id,
                    row_number,
                )
                continue
            seen_ids.add(source_id)
            text = row.get(columns["text"], "").strip()
            if not text:
                report.missing_text_records += 1
                self._reject(report, "missing_text", "Mapped text is blank", source_id, row_number)
                continue
            try:
                occurred_at = _parse_mapped_timestamp(row.get(columns["timestamp"], ""), time_zone)
            except ValueError as error:
                self._reject(report, "invalid_timestamp", str(error), source_id, row_number)
                continue

            rating = None
            rating_column = columns.get("rating")
            if rating_column and row.get(rating_column, "").strip():
                try:
                    rating = Rating(
                        value=Decimal(row[rating_column].strip()),
                        scale_min=rating_min,
                        scale_max=rating_max,
                    )
                except (InvalidOperation, CanonicalRecordError):
                    self._reject(
                        report,
                        "invalid_rating",
                        f"Mapped rating is invalid: {row.get(rating_column)!r}",
                        source_id,
                        row_number,
                    )
                    continue

            related_products: tuple[RelatedProduct, ...] = ()
            product_id = _mapped_value(row, columns, "product_id")
            if product_id is not None:
                related_products = (
                    RelatedProduct(
                        product_id=product_id,
                        product_name=_mapped_value(row, columns, "product_name"),
                        category=_mapped_value(row, columns, "category"),
                        category_language=language,
                    ),
                )

            try:
                record = FeedbackRecord(
                    feedback_id=canonical_feedback_id(self.provider_id, source_id),
                    source=SourceReference(
                        provider_id=self.provider_id,
                        dataset_name=dataset_name,
                        dataset_version=dataset_version,
                        source_record_id=source_id,
                    ),
                    original_text=text,
                    title=_mapped_value(row, columns, "title"),
                    occurred_at=occurred_at,
                    rating=rating,
                    related_products=related_products,
                    order_id=_mapped_value(row, columns, "order_id"),
                    channel=channel,
                    language=language,
                )
            except CanonicalRecordError as error:
                self._reject(
                    report, "canonical_validation_failed", str(error), source_id, row_number
                )
                continue
            records.append(record)
            report.valid_records += 1

        if report.records_discovered == 0:
            report.error(
                "empty_dataset",
                "CSV contains no records",
                source_file=self._source_path.name,
                blocking=True,
            )
        return self._result(
            tuple(records),
            report,
            checksum,
            dataset_name,
            dataset_version,
            language,
            license_name,
            attribution,
        )

    def _read_mapping(self, report: ReportBuilder) -> dict[str, Any]:
        if not self._mapping_path.is_file():
            report.error(
                "mapping_not_found",
                f"Mapping file does not exist: {self._mapping_path}",
                source_file=str(self._mapping_path),
                blocking=True,
            )
            return {}
        try:
            value = yaml.safe_load(self._mapping_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, yaml.YAMLError, OSError) as error:
            report.error(
                "invalid_mapping",
                f"Could not read mapping: {error}",
                source_file=self._mapping_path.name,
                blocking=True,
            )
            return {}
        if not isinstance(value, dict):
            report.error(
                "invalid_mapping",
                "Mapping root must be an object",
                source_file=self._mapping_path.name,
                blocking=True,
            )
            return {}
        if value.get("version") != 1:
            report.error(
                "unsupported_mapping_version",
                "Only mapping version 1 is supported",
                source_file=self._mapping_path.name,
                blocking=True,
            )
        return value

    def _read_csv(
        self, mapped_columns: set[str], report: ReportBuilder
    ) -> list[tuple[int, dict[str, str]]] | None:
        if not self._source_path.is_file():
            report.error(
                "source_not_found",
                f"CSV file does not exist: {self._source_path}",
                source_file=str(self._source_path),
                blocking=True,
            )
            return None
        try:
            with self._source_path.open("r", encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source)
                headers = set(reader.fieldnames or [])
                missing = sorted(mapped_columns - headers)
                if missing:
                    report.error(
                        "unsupported_schema",
                        f"CSV is missing mapped columns: {', '.join(missing)}",
                        source_file=self._source_path.name,
                        blocking=True,
                    )
                    return None
                rows: list[tuple[int, dict[str, str]]] = []
                # Row numbers are logical CSV record positions, with the header at row 1.
                for row_number, row in enumerate(reader, start=2):
                    report.records_discovered += 1
                    missing_cells = sorted(
                        column for column in mapped_columns if row.get(column) is None
                    )
                    extra_value = row.get(None)
                    extra_cells = (
                        len(extra_value)
                        if isinstance(extra_value, list)
                        else int(extra_value is not None)
                    )
                    if missing_cells or extra_cells:
                        details: list[str] = []
                        if missing_cells:
                            details.append(
                                f"{len(missing_cells)} missing mapped cell(s): "
                                f"{', '.join(missing_cells)}"
                            )
                        if extra_cells:
                            details.append(f"{extra_cells} extra cell(s)")
                        self._reject(
                            report,
                            "malformed_csv_row",
                            f"Malformed CSV row ({'; '.join(details)})",
                            None,
                            row_number,
                        )
                        continue
                    rows.append(
                        (
                            row_number,
                            {
                                key: value
                                for key, value in row.items()
                                if key is not None and isinstance(value, str)
                            },
                        )
                    )
                return rows
        except UnicodeDecodeError as error:
            report.error(
                "unexpected_encoding",
                f"CSV must be UTF-8: {error}",
                source_file=self._source_path.name,
                blocking=True,
            )
        except (csv.Error, OSError) as error:
            report.error(
                "source_read_failed",
                f"Could not read CSV: {error}",
                source_file=self._source_path.name,
                blocking=True,
            )
        return None

    def _time_zone(self, mapping: dict[str, Any], report: ReportBuilder) -> ZoneInfo:
        name = str(mapping.get("timezone", "UTC"))
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            report.error(
                "invalid_mapping_timezone",
                f"Unknown mapping timezone: {name}",
                source_file=self._mapping_path.name,
                blocking=True,
            )
            return ZoneInfo("UTC")

    def _rating_scale(
        self, mapping: dict[str, Any], report: ReportBuilder
    ) -> tuple[Decimal, Decimal]:
        value = mapping.get("rating_scale", [1, 5])
        try:
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError
            minimum, maximum = Decimal(str(value[0])), Decimal(str(value[1]))
            if minimum >= maximum:
                raise ValueError
            return minimum, maximum
        except (InvalidOperation, ValueError):
            report.error(
                "invalid_rating_scale",
                "rating_scale must be [minimum, maximum] with minimum below maximum",
                source_file=self._mapping_path.name,
                blocking=True,
            )
            return Decimal(1), Decimal(5)

    def _checksum(self) -> str:
        digest = hashlib.sha256()
        for label, path in (("mapping", self._mapping_path), ("source", self._source_path)):
            digest.update(label.encode())
            if path.is_file():
                with path.open("rb") as source:
                    while chunk := source.read(1024 * 1024):
                        digest.update(chunk)
        return digest.hexdigest()

    def _reject(
        self,
        report: ReportBuilder,
        code: str,
        message: str,
        source_id: str | None,
        row_number: int,
    ) -> None:
        report.rejected_records += 1
        report.error(
            code,
            message,
            source_record_id=source_id,
            source_file=self._source_path.name,
            row_number=row_number,
        )

    def _result(
        self,
        records: tuple[FeedbackRecord, ...],
        report: ReportBuilder,
        checksum: str,
        dataset_name: str,
        dataset_version: str,
        language: str | None,
        license_name: str,
        attribution: str,
    ) -> DatasetLoadResult:
        return DatasetLoadResult(
            records=records,
            metadata=metadata_for_records(
                provider_id=self.provider_id,
                dataset_name=dataset_name,
                dataset_version=dataset_version,
                source_uri=f"file:{self._source_path.name}",
                license_name=license_name,
                attribution=attribution,
                default_language=language,
                checksum_sha256=checksum,
                records=records,
            ),
            validation=report.freeze(),
        )


def _mapped_value(row: dict[str, str], columns: dict[str, str], key: str) -> str | None:
    column = columns.get(key)
    return None if column is None else _optional_text(row.get(column))


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _parse_mapped_timestamp(value: str, time_zone: ZoneInfo) -> datetime:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("mapped timestamp is blank")
    try:
        parsed = datetime.fromisoformat(
            cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
        )
    except ValueError as error:
        raise ValueError(f"mapped timestamp is invalid: {value!r}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        candidates = tuple(parsed.replace(tzinfo=time_zone, fold=fold) for fold in (0, 1))
        valid_candidates = tuple(
            candidate
            for candidate in candidates
            if candidate.astimezone(UTC).astimezone(time_zone).replace(tzinfo=None) == parsed
        )
        zone_name = time_zone.key
        if not valid_candidates:
            raise ValueError(
                f"mapped timestamp is nonexistent in {zone_name}; include an explicit UTC offset"
            )
        if len({candidate.utcoffset() for candidate in valid_candidates}) > 1:
            raise ValueError(
                f"mapped timestamp is ambiguous in {zone_name}; include an explicit UTC offset"
            )
        parsed = valid_candidates[0]
    return parsed.astimezone(UTC)
