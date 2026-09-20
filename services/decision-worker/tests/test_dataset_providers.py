"""Olist, synthetic, and generic CSV provider behavior."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from feedback_intelligence_worker.data.provider import DatasetProvider
from feedback_intelligence_worker.data.providers import (
    MappedCsvDatasetProvider,
    OlistDatasetProvider,
    SyntheticDatasetProvider,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures"


def synthetic_provider() -> SyntheticDatasetProvider:
    return SyntheticDatasetProvider(REPOSITORY_ROOT / "data/demo/feedback.jsonl")


def olist_provider() -> OlistDatasetProvider:
    return OlistDatasetProvider(FIXTURES / "olist")


def mapped_csv_provider(
    tmp_path: Path, csv_content: str, *, timezone: str = "UTC"
) -> MappedCsvDatasetProvider:
    source = tmp_path / "feedback.csv"
    mapping = tmp_path / "mapping.yaml"
    source.write_text(csv_content, encoding="utf-8")
    mapping.write_text(
        f"""\
version: 1
dataset_name: Test export
timezone: {timezone}
columns:
  id: review_id
  text: comment
  timestamp: created_at
""",
        encoding="utf-8",
    )
    return MappedCsvDatasetProvider(source, mapping)


@pytest.mark.parametrize("provider", [synthetic_provider(), olist_provider()])
def test_provider_conformance(provider: DatasetProvider) -> None:
    assert isinstance(provider, DatasetProvider)

    result = provider.load_feedback()

    assert result.validation.is_usable
    assert result.records
    assert result.metadata.provider_id == provider.provider_id
    assert result.metadata.record_count == len(result.records)
    assert provider.metadata() == result.metadata
    assert provider.validate_source() == result.validation
    assert len({record.feedback_id for record in result.records}) == len(result.records)
    assert all(record.source.provider_id == provider.provider_id for record in result.records)
    assert all(record.privacy_status == "uninspected" for record in result.records)


def test_synthetic_provider_covers_demo_shapes() -> None:
    result = synthetic_provider().load_feedback()

    assert len(result.records) == 9
    assert any(len(record.related_products) > 1 for record in result.records)
    assert any(record.rating is None for record in result.records)
    assert any(record.operational_context is not None for record in result.records)
    assert any(record.language is None for record in result.records)


def test_olist_adapter_joins_facts_without_duplicating_reviews() -> None:
    result = olist_provider().load_feedback()
    records = {record.source.source_record_id: record for record in result.records}

    assert result.validation.records_discovered == 8
    assert result.validation.valid_records == 3
    assert result.validation.rejected_records == 5
    assert result.validation.duplicate_records == 1
    assert result.validation.missing_text_records == 1
    assert set(records) == {"r-normal", "r-title-only", "r-multi"}

    late = records["r-normal"]
    early = records["r-title-only"]
    multi = records["r-multi"]
    assert late.operational_context is not None
    assert late.operational_context.delivery_delta_days == 6
    assert early.operational_context is not None
    assert early.operational_context.delivery_delta_days == -2
    assert early.original_text == "Delivery was painful"
    assert multi.operational_context is not None
    assert multi.operational_context.delivered_at is None
    assert len(multi.related_products) == 2
    assert {product.product_id for product in multi.related_products} == {
        "p-computer",
        "p-chair",
    }
    computer = next(
        product for product in multi.related_products if product.product_id == "p-computer"
    )
    assert computer.quantity == 2
    assert computer.category == "computers_accessories"
    assert computer.category_language == "en"
    assert computer.seller_ids == ("s-2",)
    assert multi.operational_context.total_price is not None
    assert str(multi.operational_context.total_price.amount) == "1150.00"
    assert multi.operational_context.seller_count == 2


def test_olist_adapter_reports_each_rejection_reason() -> None:
    report = olist_provider().validate_source()
    codes = {issue.code for issue in report.issues}

    assert {
        "text_fallback_to_title",
        "missing_text",
        "invalid_timestamp",
        "invalid_order_relationship",
        "invalid_rating",
        "duplicate_source_record",
    } <= codes


def test_olist_output_contains_no_source_column_names() -> None:
    result = olist_provider().load_feedback()
    serialized = json.dumps([record.to_dict() for record in result.records])

    assert "review_comment_message" not in serialized
    assert "order_delivered_customer_date" not in serialized
    assert "freight_value" not in serialized


def test_olist_preserves_portuguese_categories_without_translation(tmp_path: Path) -> None:
    source = tmp_path / "olist"
    shutil.copytree(FIXTURES / "olist", source)
    (source / "product_category_name_translation.csv").unlink()

    result = OlistDatasetProvider(source).load_feedback()
    normal = next(
        record for record in result.records if record.source.source_record_id == "r-normal"
    )

    assert normal.related_products[0].category == "beleza_saude"
    assert normal.related_products[0].category_language == "pt-BR"
    assert any(
        issue.code == "category_translation_unavailable" for issue in result.validation.issues
    )


def test_olist_reports_unexpected_encoding_as_blocking(tmp_path: Path) -> None:
    source = tmp_path / "olist"
    shutil.copytree(FIXTURES / "olist", source)
    (source / "olist_order_reviews_dataset.csv").write_bytes(b"\xff\xfe\x00")

    result = OlistDatasetProvider(source).load_feedback()

    assert not result.validation.is_usable
    assert any(issue.code == "unexpected_encoding" for issue in result.validation.issues)


def test_olist_reports_unsupported_schema_as_blocking(tmp_path: Path) -> None:
    source = tmp_path / "olist"
    shutil.copytree(FIXTURES / "olist", source)
    (source / "olist_order_reviews_dataset.csv").write_text(
        "review_id,order_id\nr-1,o-1\n", encoding="utf-8"
    )

    result = OlistDatasetProvider(source).load_feedback()

    assert not result.validation.is_usable
    assert any(issue.code == "unsupported_schema" for issue in result.validation.issues)


def test_mapped_csv_provider_normalizes_level_b_feedback() -> None:
    provider = MappedCsvDatasetProvider(
        FIXTURES / "csv/customer-feedback.csv",
        FIXTURES / "csv/mapping.yaml",
    )

    result = provider.load_feedback()

    assert result.validation.is_usable
    assert len(result.records) == 2
    assert result.records[0].source.provider_id == "csv"
    assert result.records[0].related_products[0].product_id == "SKU-1"
    assert result.records[1].related_products == ()
    assert result.records[1].order_id == "ORDER-2"


@pytest.mark.parametrize(
    ("header", "row", "missing_column"),
    [
        (
            "review_id,created_at,comment",
            "missing-text,2026-03-01T10:00:00Z",
            "comment",
        ),
        ("review_id,comment,created_at", "missing-date,Feedback", "created_at"),
    ],
)
def test_mapped_csv_rejects_missing_mapped_cells(
    tmp_path: Path, header: str, row: str, missing_column: str
) -> None:
    result = mapped_csv_provider(tmp_path, f"{header}\n{row}\n").load_feedback()

    assert result.records == ()
    assert result.validation.records_discovered == 1
    assert result.validation.rejected_records == 1
    issue = next(issue for issue in result.validation.issues if issue.code == "malformed_csv_row")
    assert issue.row_number == 2
    assert f"1 missing mapped cell(s): {missing_column}" in issue.message


def test_mapped_csv_rejects_extra_cells_and_preserves_valid_rows(tmp_path: Path) -> None:
    result = mapped_csv_provider(
        tmp_path,
        "review_id,comment,created_at\n"
        "valid,Useful feedback,2026-03-01T10:00:00Z\n"
        "extra,Malformed feedback,2026-03-01T10:00:00Z,one,two\n",
    ).load_feedback()

    assert [record.source.source_record_id for record in result.records] == ["valid"]
    assert result.validation.records_discovered == 2
    assert result.validation.valid_records == 1
    assert result.validation.rejected_records == 1
    issue = next(issue for issue in result.validation.issues if issue.code == "malformed_csv_row")
    assert issue.row_number == 3
    assert "2 extra cell(s)" in issue.message


def test_mapped_csv_preserves_row_numbers_after_filtering_malformed_rows(
    tmp_path: Path,
) -> None:
    result = mapped_csv_provider(
        tmp_path,
        "review_id,comment,created_at\n"
        "extra,Malformed feedback,2026-03-01T10:00:00Z,surplus\n"
        "bad-date,Feedback,not-a-timestamp\n",
    ).load_feedback()

    assert result.records == ()
    assert result.validation.records_discovered == 2
    assert result.validation.rejected_records == 2
    issues = {
        issue.code: issue for issue in result.validation.issues if issue.row_number is not None
    }
    assert issues["malformed_csv_row"].row_number == 2
    assert issues["invalid_timestamp"].row_number == 3


def test_mapped_csv_rejects_blank_timestamp(tmp_path: Path) -> None:
    result = mapped_csv_provider(
        tmp_path,
        "review_id,comment,created_at\nblank-date,Feedback,\n",
    ).load_feedback()

    assert result.records == ()
    issue = next(issue for issue in result.validation.issues if issue.code == "invalid_timestamp")
    assert issue.row_number == 2
    assert issue.message == "mapped timestamp is blank"


@pytest.mark.parametrize(
    ("local_timestamp", "problem"),
    [
        ("2025-10-26T02:30:00", "ambiguous"),
        ("2025-03-30T02:30:00", "nonexistent"),
    ],
)
def test_mapped_csv_rejects_unsafe_local_dst_timestamps(
    tmp_path: Path, local_timestamp: str, problem: str
) -> None:
    result = mapped_csv_provider(
        tmp_path,
        f"review_id,comment,created_at\nunsafe,Feedback,{local_timestamp}\n",
        timezone="Europe/Stockholm",
    ).load_feedback()

    assert result.records == ()
    issue = next(issue for issue in result.validation.issues if issue.code == "invalid_timestamp")
    assert issue.row_number == 2
    assert problem in issue.message
    assert "include an explicit UTC offset" in issue.message


def test_mapped_csv_accepts_explicit_offset_during_dst_overlap(tmp_path: Path) -> None:
    result = mapped_csv_provider(
        tmp_path,
        "review_id,comment,created_at\noffset,Feedback,2025-10-26T02:30:00+02:00\n",
        timezone="Europe/Stockholm",
    ).load_feedback()

    assert result.validation.is_usable
    assert len(result.records) == 1
    assert result.records[0].occurred_at.isoformat() == "2025-10-26T00:30:00+00:00"
