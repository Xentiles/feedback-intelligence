"""Deterministic, AI-free profiling for canonical feedback records."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from feedback_intelligence_worker.data.models import DatasetLoadResult, JsonValue, utc_iso


@dataclass(frozen=True, slots=True)
class DatasetProfile:
    record_count: int
    date_start: str | None
    date_end: str | None
    rating_distribution: dict[str, int]
    language_distribution: dict[str, int]
    missing_text_percentage: float
    product_count: int
    category_count: int
    reviews_per_month: dict[str, int]
    duplicate_count: int
    rejected_count: int

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "record_count": self.record_count,
            "date_range": (
                None
                if self.date_start is None
                else {"start": self.date_start, "end": self.date_end}
            ),
            "rating_distribution": cast(JsonValue, self.rating_distribution),
            "language_distribution": cast(JsonValue, self.language_distribution),
            "missing_text_percentage": self.missing_text_percentage,
            "product_count": self.product_count,
            "category_count": self.category_count,
            "reviews_per_month": cast(JsonValue, self.reviews_per_month),
            "duplicate_count": self.duplicate_count,
            "rejected_count": self.rejected_count,
        }


def profile_dataset(result: DatasetLoadResult) -> DatasetProfile:
    records = result.records
    dates = sorted(record.occurred_at for record in records)
    ratings = Counter(
        _decimal_label(record.rating.value) for record in records if record.rating is not None
    )
    languages = Counter(record.language or "unknown" for record in records)
    products = {product.product_id for record in records for product in record.related_products}
    categories = {
        product.category
        for record in records
        for product in record.related_products
        if product.category is not None
    }
    months = Counter(record.occurred_at.strftime("%Y-%m") for record in records)
    discovered = result.validation.records_discovered
    missing_percentage = (
        0.0
        if discovered == 0
        else round(result.validation.missing_text_records / discovered * 100, 3)
    )
    return DatasetProfile(
        record_count=len(records),
        date_start=None if not dates else utc_iso(dates[0]),
        date_end=None if not dates else utc_iso(dates[-1]),
        rating_distribution=dict(sorted(ratings.items())),
        language_distribution=dict(sorted(languages.items())),
        missing_text_percentage=missing_percentage,
        product_count=len(products),
        category_count=len(categories),
        reviews_per_month=dict(sorted(months.items())),
        duplicate_count=result.validation.duplicate_records,
        rejected_count=result.validation.rejected_records,
    )


def _decimal_label(value: Decimal) -> str:
    formatted = format(value, "f")
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted
