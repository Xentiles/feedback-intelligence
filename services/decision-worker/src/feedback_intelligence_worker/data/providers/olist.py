"""Adapter for the Brazilian E-Commerce Public Dataset by Olist."""

from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from feedback_intelligence_worker.data.models import (
    CanonicalRecordError,
    DatasetLoadResult,
    DatasetMetadata,
    FeedbackRecord,
    Money,
    OperationalContext,
    Rating,
    RelatedProduct,
    SourceReference,
    ValidationReport,
    canonical_feedback_id,
)
from feedback_intelligence_worker.data.support import (
    ReportBuilder,
    checksum_files,
    metadata_for_records,
)

OLIST_HANDLE = "olistbr/brazilian-ecommerce"
OLIST_SOURCE_URI = f"https://www.kaggle.com/datasets/{OLIST_HANDLE}"
OLIST_DATASET_NAME = "Brazilian E-Commerce Public Dataset by Olist"
OLIST_LICENSE = "CC-BY-NC-SA-4.0"
OLIST_ATTRIBUTION = "Olist, Brazilian E-Commerce Public Dataset"
OLIST_TIME_ZONE = ZoneInfo("America/Sao_Paulo")
EMPTY_CHECKSUM = hashlib.sha256(b"").hexdigest()

REVIEWS = "olist_order_reviews_dataset.csv"
ORDERS = "olist_orders_dataset.csv"
ORDER_ITEMS = "olist_order_items_dataset.csv"
PRODUCTS = "olist_products_dataset.csv"
TRANSLATIONS = "product_category_name_translation.csv"

REQUIRED_COLUMNS: dict[str, set[str]] = {
    REVIEWS: {
        "review_id",
        "order_id",
        "review_score",
        "review_comment_title",
        "review_comment_message",
        "review_creation_date",
    },
    ORDERS: {
        "order_id",
        "order_status",
        "order_purchase_timestamp",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    },
    ORDER_ITEMS: {
        "order_id",
        "order_item_id",
        "product_id",
        "seller_id",
        "price",
        "freight_value",
    },
    PRODUCTS: {"product_id", "product_category_name"},
}

TRANSLATION_COLUMNS = {"product_category_name", "product_category_name_english"}
CsvRow = dict[str, str]


@dataclass(slots=True)
class _ProductAccumulator:
    product_id: str
    first_position: int
    quantity: int = 0
    sellers: set[str] = field(default_factory=set)
    price: Decimal = Decimal("0")
    freight: Decimal = Decimal("0")
    has_price: bool = False
    has_freight: bool = False


class OlistDatasetProvider:
    """Normalize Olist review/order tables without leaking their schema downstream."""

    provider_id = "olist"

    def __init__(self, source_directory: Path) -> None:
        self._source_directory = source_directory
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
        files = self._discover_files(report)
        available_paths = list(files.values())
        checksum = (
            checksum_files(available_paths, relative_to=self._source_directory)
            if available_paths
            else EMPTY_CHECKSUM
        )
        dataset_version = f"source-sha256:{checksum[:12]}"

        if any(issue.blocking for issue in report.issues):
            return self._result((), report, checksum, dataset_version)

        tables: dict[str, list[CsvRow]] = {}
        for filename, columns in REQUIRED_COLUMNS.items():
            table = self._read_table(files[filename], columns, report)
            if table is not None:
                tables[filename] = table

        translations: list[CsvRow] = []
        if TRANSLATIONS in files:
            loaded_translations = self._read_table(files[TRANSLATIONS], TRANSLATION_COLUMNS, report)
            if loaded_translations is not None:
                translations = loaded_translations
        else:
            report.warning(
                "category_translation_unavailable",
                "Category translation table was not found; Portuguese category names are preserved",
                source_file=TRANSLATIONS,
            )

        if any(issue.blocking for issue in report.issues):
            return self._result((), report, checksum, dataset_version)

        reviews = tables[REVIEWS]
        if not reviews:
            report.error(
                "empty_dataset",
                "Olist reviews table contains no records",
                source_file=REVIEWS,
                blocking=True,
            )
            return self._result((), report, checksum, dataset_version)

        orders = self._unique_index(tables[ORDERS], "order_id", ORDERS, report)
        products = self._unique_index(tables[PRODUCTS], "product_id", PRODUCTS, report)
        translation_index = self._translation_index(translations, report)
        items_by_order = self._group_items(tables[ORDER_ITEMS], orders, report)
        if any(issue.blocking for issue in report.issues):
            return self._result((), report, checksum, dataset_version)

        records: list[FeedbackRecord] = []
        seen_review_ids: set[str] = set()
        for row_number, review in enumerate(reviews, start=2):
            report.records_discovered += 1
            source_record_id = review.get("review_id", "").strip()
            issue_id = source_record_id or f"row:{row_number}"
            if not source_record_id:
                self._reject(
                    report,
                    "missing_source_id",
                    "Review is missing review_id",
                    issue_id,
                    row_number,
                )
                continue
            if source_record_id in seen_review_ids:
                report.duplicate_records += 1
                self._reject(
                    report,
                    "duplicate_source_record",
                    f"Duplicate review_id: {source_record_id}",
                    source_record_id,
                    row_number,
                )
                continue
            seen_review_ids.add(source_record_id)

            order_id = review.get("order_id", "").strip()
            order = orders.get(order_id)
            if not order_id or order is None:
                self._reject(
                    report,
                    "invalid_order_relationship",
                    f"Review references missing order_id: {order_id or '<blank>'}",
                    source_record_id,
                    row_number,
                )
                continue

            title = _clean(review.get("review_comment_title"))
            body = _clean(review.get("review_comment_message"))
            text_basis = "body"
            if body is None and title is not None:
                body = title
                text_basis = "title"
                report.warning(
                    "text_fallback_to_title",
                    "Review body is empty; canonical text uses the non-empty title",
                    source_record_id=source_record_id,
                    source_file=REVIEWS,
                    row_number=row_number,
                )
            if body is None:
                report.missing_text_records += 1
                self._reject(
                    report,
                    "missing_text",
                    "Review has neither body text nor title",
                    source_record_id,
                    row_number,
                )
                continue

            try:
                rating_value = Decimal(review.get("review_score", "").strip())
                if rating_value != rating_value.to_integral_value():
                    raise CanonicalRecordError("Olist review score must be an integer")
                rating = Rating(value=rating_value, scale_min=Decimal(1), scale_max=Decimal(5))
            except (InvalidOperation, CanonicalRecordError):
                self._reject(
                    report,
                    "invalid_rating",
                    f"Review score is not within the 1-5 scale: {review.get('review_score')!r}",
                    source_record_id,
                    row_number,
                )
                continue

            try:
                occurred_at = _parse_olist_timestamp(review.get("review_creation_date", ""))
            except ValueError as error:
                self._reject(
                    report,
                    "invalid_timestamp",
                    str(error),
                    source_record_id,
                    row_number,
                )
                continue

            related_products, total_price, total_freight, sellers = self._products_for_order(
                order_id=order_id,
                item_rows=items_by_order.get(order_id, []),
                products=products,
                translations=translation_index,
                report=report,
                source_record_id=source_record_id,
            )
            context = self._operational_context(
                order,
                total_price=total_price,
                total_freight=total_freight,
                seller_count=len(sellers),
                report=report,
                source_record_id=source_record_id,
            )
            try:
                record = FeedbackRecord(
                    feedback_id=canonical_feedback_id(self.provider_id, source_record_id),
                    source=SourceReference(
                        provider_id=self.provider_id,
                        dataset_name=OLIST_DATASET_NAME,
                        dataset_version=dataset_version,
                        source_record_id=source_record_id,
                    ),
                    original_text=body,
                    title=title,
                    occurred_at=occurred_at,
                    rating=rating,
                    related_products=related_products,
                    order_id=order_id,
                    channel="ecommerce_review",
                    language="pt-BR",
                    metadata={"text_basis": text_basis},
                    operational_context=context,
                )
            except CanonicalRecordError as error:
                self._reject(
                    report,
                    "canonical_validation_failed",
                    str(error),
                    source_record_id,
                    row_number,
                )
                continue
            records.append(record)
            report.valid_records += 1

        return self._result(tuple(records), report, checksum, dataset_version)

    def _discover_files(self, report: ReportBuilder) -> dict[str, Path]:
        files: dict[str, Path] = {}
        if not self._source_directory.is_dir():
            report.error(
                "source_directory_not_found",
                f"Olist source directory does not exist: {self._source_directory}",
                blocking=True,
            )
            return files
        for filename in (*REQUIRED_COLUMNS, TRANSLATIONS):
            matches = sorted(self._source_directory.rglob(filename))
            if not matches:
                if filename in REQUIRED_COLUMNS:
                    report.error(
                        "missing_source_table",
                        f"Required Olist table is missing: {filename}",
                        source_file=filename,
                        blocking=True,
                    )
                continue
            if len(matches) > 1:
                report.error(
                    "ambiguous_source_table",
                    f"Found more than one {filename}; keep exactly one source copy",
                    source_file=filename,
                    blocking=True,
                )
                continue
            files[filename] = matches[0]
        return files

    def _read_table(
        self, path: Path, required_columns: set[str], report: ReportBuilder
    ) -> list[CsvRow] | None:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source)
                headers = set(reader.fieldnames or [])
                missing = sorted(required_columns - headers)
                if missing:
                    report.error(
                        "unsupported_schema",
                        f"{path.name} is missing columns: {', '.join(missing)}",
                        source_file=path.name,
                        blocking=True,
                    )
                    return None
                return [dict(row) for row in reader]
        except UnicodeDecodeError as error:
            report.error(
                "unexpected_encoding",
                f"{path.name} must be UTF-8: {error}",
                source_file=path.name,
                blocking=True,
            )
        except (csv.Error, OSError) as error:
            report.error(
                "source_read_failed",
                f"Could not read {path.name}: {error}",
                source_file=path.name,
                blocking=True,
            )
        return None

    def _unique_index(
        self, rows: list[CsvRow], key: str, filename: str, report: ReportBuilder
    ) -> dict[str, CsvRow]:
        index: dict[str, CsvRow] = {}
        for row_number, row in enumerate(rows, start=2):
            value = row.get(key, "").strip()
            if not value:
                report.warning(
                    "missing_relationship_key",
                    f"Ignoring {filename} row with blank {key}",
                    source_file=filename,
                    row_number=row_number,
                )
                continue
            if value in index:
                report.error(
                    "duplicate_relationship_key",
                    f"{filename} contains duplicate {key}: {value}",
                    source_file=filename,
                    row_number=row_number,
                    blocking=True,
                )
                continue
            index[value] = row
        return index

    def _translation_index(self, rows: list[CsvRow], report: ReportBuilder) -> dict[str, str]:
        translations: dict[str, str] = {}
        for row_number, row in enumerate(rows, start=2):
            source_name = row.get("product_category_name", "").strip()
            translated = row.get("product_category_name_english", "").strip()
            if not source_name or not translated:
                report.warning(
                    "invalid_category_translation",
                    "Ignoring category translation with a blank source or target value",
                    source_file=TRANSLATIONS,
                    row_number=row_number,
                )
                continue
            if source_name in translations:
                report.warning(
                    "duplicate_category_translation",
                    f"Keeping the first translation for category: {source_name}",
                    source_file=TRANSLATIONS,
                    row_number=row_number,
                )
                continue
            translations[source_name] = translated
        return translations

    def _group_items(
        self, rows: list[CsvRow], orders: dict[str, CsvRow], report: ReportBuilder
    ) -> dict[str, list[CsvRow]]:
        grouped: dict[str, list[CsvRow]] = defaultdict(list)
        for row_number, row in enumerate(rows, start=2):
            order_id = row.get("order_id", "").strip()
            product_id = row.get("product_id", "").strip()
            if not order_id or not product_id:
                report.warning(
                    "invalid_order_item",
                    "Ignoring order item with blank order_id or product_id",
                    source_file=ORDER_ITEMS,
                    row_number=row_number,
                )
                continue
            if order_id not in orders:
                report.warning(
                    "orphan_order_item",
                    f"Ignoring order item whose order does not exist: {order_id}",
                    source_file=ORDER_ITEMS,
                    row_number=row_number,
                )
                continue
            grouped[order_id].append(row)
        return grouped

    def _products_for_order(
        self,
        *,
        order_id: str,
        item_rows: list[CsvRow],
        products: dict[str, CsvRow],
        translations: dict[str, str],
        report: ReportBuilder,
        source_record_id: str,
    ) -> tuple[tuple[RelatedProduct, ...], Money | None, Money | None, set[str]]:
        if not item_rows:
            report.warning(
                "order_has_no_items",
                f"Order has no usable item relationship: {order_id}",
                source_record_id=source_record_id,
                source_file=ORDER_ITEMS,
            )
            return (), None, None, set()

        aggregate: dict[str, _ProductAccumulator] = {}
        all_sellers: set[str] = set()
        for position, row in enumerate(item_rows):
            product_id = row["product_id"].strip()
            item = aggregate.setdefault(
                product_id,
                _ProductAccumulator(product_id=product_id, first_position=position),
            )
            item.quantity += 1
            seller_id = row.get("seller_id", "").strip()
            if seller_id:
                item.sellers.add(seller_id)
                all_sellers.add(seller_id)
            parsed_price = self._parse_money(
                row.get("price", ""), "invalid_price", report, source_record_id
            )
            if parsed_price is not None:
                item.price += parsed_price
                item.has_price = True
            parsed_freight = self._parse_money(
                row.get("freight_value", ""),
                "invalid_freight_cost",
                report,
                source_record_id,
            )
            if parsed_freight is not None:
                item.freight += parsed_freight
                item.has_freight = True

        related: list[RelatedProduct] = []
        for item in sorted(aggregate.values(), key=lambda value: value.first_position):
            product = products.get(item.product_id)
            raw_category = None if product is None else _clean(product.get("product_category_name"))
            if product is None:
                report.warning(
                    "missing_product_relationship",
                    f"Product metadata is missing for product_id: {item.product_id}",
                    source_record_id=source_record_id,
                    source_file=PRODUCTS,
                )
            translated_category = None if raw_category is None else translations.get(raw_category)
            related.append(
                RelatedProduct(
                    product_id=item.product_id,
                    category=translated_category or raw_category,
                    category_language="en"
                    if translated_category
                    else ("pt-BR" if raw_category else None),
                    quantity=item.quantity,
                    seller_ids=tuple(sorted(item.sellers)),
                    price=Money(item.price, "BRL") if item.has_price else None,
                    freight_cost=Money(item.freight, "BRL") if item.has_freight else None,
                )
            )

        price_values = [item.price for item in aggregate.values() if item.has_price]
        freight_values = [item.freight for item in aggregate.values() if item.has_freight]
        total_price = Money(sum(price_values, Decimal("0")), "BRL") if price_values else None
        total_freight = Money(sum(freight_values, Decimal("0")), "BRL") if freight_values else None
        return tuple(related), total_price, total_freight, all_sellers

    def _parse_money(
        self,
        raw_value: str,
        code: str,
        report: ReportBuilder,
        source_record_id: str,
    ) -> Decimal | None:
        try:
            return Decimal(raw_value.strip())
        except InvalidOperation:
            report.warning(
                code,
                f"Ignoring invalid monetary value: {raw_value!r}",
                source_record_id=source_record_id,
                source_file=ORDER_ITEMS,
            )
            return None

    def _operational_context(
        self,
        order: CsvRow,
        *,
        total_price: Money | None,
        total_freight: Money | None,
        seller_count: int,
        report: ReportBuilder,
        source_record_id: str,
    ) -> OperationalContext:
        purchased = self._optional_timestamp(
            order.get("order_purchase_timestamp", ""),
            "purchase timestamp",
            report,
            source_record_id,
        )
        delivered = self._optional_timestamp(
            order.get("order_delivered_customer_date", ""),
            "actual delivery timestamp",
            report,
            source_record_id,
        )
        expected = self._optional_timestamp(
            order.get("order_estimated_delivery_date", ""),
            "estimated delivery timestamp",
            report,
            source_record_id,
        )
        delta = None
        if delivered is not None and expected is not None:
            delta = round((delivered - expected).total_seconds() / 86_400, 3)
        return OperationalContext(
            purchased_at=purchased,
            delivered_at=delivered,
            expected_delivery_at=expected,
            delivery_delta_days=delta,
            order_status=_clean(order.get("order_status")),
            total_price=total_price,
            total_freight_cost=total_freight,
            seller_count=seller_count,
        )

    def _optional_timestamp(
        self,
        raw_value: str,
        label: str,
        report: ReportBuilder,
        source_record_id: str,
    ) -> datetime | None:
        if not raw_value.strip():
            return None
        try:
            return _parse_olist_timestamp(raw_value)
        except ValueError as error:
            report.warning(
                "invalid_operational_timestamp",
                f"Ignoring {label}: {error}",
                source_record_id=source_record_id,
                source_file=ORDERS,
            )
            return None

    def _reject(
        self,
        report: ReportBuilder,
        code: str,
        message: str,
        source_record_id: str,
        row_number: int,
    ) -> None:
        report.rejected_records += 1
        report.error(
            code,
            message,
            source_record_id=source_record_id,
            source_file=REVIEWS,
            row_number=row_number,
        )

    def _result(
        self,
        records: tuple[FeedbackRecord, ...],
        report: ReportBuilder,
        checksum: str,
        dataset_version: str,
    ) -> DatasetLoadResult:
        return DatasetLoadResult(
            records=records,
            metadata=metadata_for_records(
                provider_id=self.provider_id,
                dataset_name=OLIST_DATASET_NAME,
                dataset_version=dataset_version,
                source_uri=OLIST_SOURCE_URI,
                license_name=OLIST_LICENSE,
                attribution=OLIST_ATTRIBUTION,
                default_language="pt-BR",
                checksum_sha256=checksum,
                records=records,
            ),
            validation=report.freeze(),
        )


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _parse_olist_timestamp(raw_value: str) -> datetime:
    value = raw_value.strip()
    if not value:
        raise ValueError("timestamp is blank")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"invalid Olist timestamp: {raw_value!r}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=OLIST_TIME_ZONE)
    return parsed.astimezone(UTC)
