"""Canonical dataset models shared by every source adapter."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid5

SCHEMA_VERSION = "feedback-record/1.0.0"
METADATA_SCHEMA_VERSION = "dataset-metadata/1.0.0"
FEEDBACK_ID_NAMESPACE = UUID("f31fe881-b783-42b2-851e-ce62ab486855")

type JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


class CanonicalRecordError(ValueError):
    """Raised when a source row cannot become a canonical record."""


class IssueSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


def canonical_feedback_id(provider_id: str, source_record_id: str) -> str:
    """Return a stable identifier independent of a dataset refresh version."""
    return str(uuid5(FEEDBACK_ID_NAMESPACE, f"{provider_id}:{source_record_id}"))


def utc_iso(value: datetime) -> str:
    """Serialize an aware timestamp in a single canonical UTC form."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise CanonicalRecordError("timestamps must include a timezone")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_utc_iso(value: str) -> datetime:
    """Parse a canonical timestamp and require an explicit offset."""
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise CanonicalRecordError(f"invalid timestamp: {value!r}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalRecordError(f"timestamp lacks an offset: {value!r}")
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if len(self.currency) != 3 or not self.currency.isupper():
            raise CanonicalRecordError("currency must be a three-letter uppercase code")

    def to_dict(self) -> dict[str, JsonValue]:
        return {"amount": format(self.amount, "f"), "currency": self.currency}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Money:
        return cls(amount=Decimal(str(value["amount"])), currency=str(value["currency"]))


@dataclass(frozen=True, slots=True)
class Rating:
    value: Decimal
    scale_min: Decimal
    scale_max: Decimal

    def __post_init__(self) -> None:
        if self.scale_min >= self.scale_max:
            raise CanonicalRecordError("rating scale minimum must be below its maximum")
        if not self.scale_min <= self.value <= self.scale_max:
            raise CanonicalRecordError("rating value is outside its declared scale")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "value": float(self.value),
            "scale_min": float(self.scale_min),
            "scale_max": float(self.scale_max),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Rating:
        return cls(
            value=Decimal(str(value["value"])),
            scale_min=Decimal(str(value["scale_min"])),
            scale_max=Decimal(str(value["scale_max"])),
        )


@dataclass(frozen=True, slots=True)
class RelatedProduct:
    product_id: str
    product_name: str | None = None
    category: str | None = None
    category_language: str | None = None
    quantity: int = 1
    seller_ids: tuple[str, ...] = ()
    price: Money | None = None
    freight_cost: Money | None = None

    def __post_init__(self) -> None:
        if not self.product_id.strip():
            raise CanonicalRecordError("product_id cannot be blank")
        if self.quantity < 1:
            raise CanonicalRecordError("product quantity must be at least one")
        if len(set(self.seller_ids)) != len(self.seller_ids):
            raise CanonicalRecordError("seller_ids must be unique")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "category": self.category,
            "category_language": self.category_language,
            "quantity": self.quantity,
            "seller_ids": list(self.seller_ids),
            "price": None if self.price is None else self.price.to_dict(),
            "freight_cost": None if self.freight_cost is None else self.freight_cost.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RelatedProduct:
        return cls(
            product_id=str(value["product_id"]),
            product_name=_optional_string(value.get("product_name")),
            category=_optional_string(value.get("category")),
            category_language=_optional_string(value.get("category_language")),
            quantity=int(value.get("quantity", 1)),
            seller_ids=tuple(str(item) for item in value.get("seller_ids", [])),
            price=None if value.get("price") is None else Money.from_dict(value["price"]),
            freight_cost=(
                None
                if value.get("freight_cost") is None
                else Money.from_dict(value["freight_cost"])
            ),
        )


@dataclass(frozen=True, slots=True)
class OperationalContext:
    purchased_at: datetime | None = None
    delivered_at: datetime | None = None
    expected_delivery_at: datetime | None = None
    delivery_delta_days: float | None = None
    order_status: str | None = None
    total_price: Money | None = None
    total_freight_cost: Money | None = None
    seller_count: int | None = None

    def __post_init__(self) -> None:
        for timestamp in (self.purchased_at, self.delivered_at, self.expected_delivery_at):
            if timestamp is not None and (
                timestamp.tzinfo is None or timestamp.utcoffset() is None
            ):
                raise CanonicalRecordError("operational timestamps must include a timezone")
        if self.seller_count is not None and self.seller_count < 0:
            raise CanonicalRecordError("seller_count cannot be negative")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "purchased_at": None if self.purchased_at is None else utc_iso(self.purchased_at),
            "delivered_at": None if self.delivered_at is None else utc_iso(self.delivered_at),
            "expected_delivery_at": (
                None if self.expected_delivery_at is None else utc_iso(self.expected_delivery_at)
            ),
            "delivery_delta_days": self.delivery_delta_days,
            "order_status": self.order_status,
            "total_price": None if self.total_price is None else self.total_price.to_dict(),
            "total_freight_cost": (
                None if self.total_freight_cost is None else self.total_freight_cost.to_dict()
            ),
            "seller_count": self.seller_count,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> OperationalContext:
        return cls(
            purchased_at=_optional_datetime(value.get("purchased_at")),
            delivered_at=_optional_datetime(value.get("delivered_at")),
            expected_delivery_at=_optional_datetime(value.get("expected_delivery_at")),
            delivery_delta_days=(
                None
                if value.get("delivery_delta_days") is None
                else float(value["delivery_delta_days"])
            ),
            order_status=_optional_string(value.get("order_status")),
            total_price=(
                None if value.get("total_price") is None else Money.from_dict(value["total_price"])
            ),
            total_freight_cost=(
                None
                if value.get("total_freight_cost") is None
                else Money.from_dict(value["total_freight_cost"])
            ),
            seller_count=None if value.get("seller_count") is None else int(value["seller_count"]),
        )


@dataclass(frozen=True, slots=True)
class SourceReference:
    provider_id: str
    dataset_name: str
    dataset_version: str
    source_record_id: str

    def __post_init__(self) -> None:
        if not all(
            item.strip()
            for item in (
                self.provider_id,
                self.dataset_name,
                self.dataset_version,
                self.source_record_id,
            )
        ):
            raise CanonicalRecordError("source reference fields cannot be blank")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "provider_id": self.provider_id,
            "dataset_name": self.dataset_name,
            "dataset_version": self.dataset_version,
            "source_record_id": self.source_record_id,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SourceReference:
        return cls(
            provider_id=str(value["provider_id"]),
            dataset_name=str(value["dataset_name"]),
            dataset_version=str(value["dataset_version"]),
            source_record_id=str(value["source_record_id"]),
        )


@dataclass(frozen=True, slots=True)
class FeedbackRecord:
    feedback_id: str
    source: SourceReference
    original_text: str
    occurred_at: datetime
    title: str | None = None
    rating: Rating | None = None
    related_products: tuple[RelatedProduct, ...] = ()
    order_id: str | None = None
    channel: str | None = None
    language: str | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)
    operational_context: OperationalContext | None = None
    privacy_status: str = "uninspected"
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        try:
            UUID(self.feedback_id)
        except ValueError as error:
            raise CanonicalRecordError("feedback_id must be a UUID") from error
        if self.schema_version != SCHEMA_VERSION:
            raise CanonicalRecordError(f"unsupported schema version: {self.schema_version}")
        if self.privacy_status != "uninspected":
            raise CanonicalRecordError("dataset providers may emit only uninspected records")
        if not self.original_text.strip():
            raise CanonicalRecordError("original_text cannot be blank")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise CanonicalRecordError("occurred_at must include a timezone")
        product_ids = [product.product_id for product in self.related_products]
        if len(product_ids) != len(set(product_ids)):
            raise CanonicalRecordError("related products must be unique by product_id")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schema_version": self.schema_version,
            "feedback_id": self.feedback_id,
            "source": self.source.to_dict(),
            "original_text": self.original_text,
            "title": self.title,
            "occurred_at": utc_iso(self.occurred_at),
            "rating": None if self.rating is None else self.rating.to_dict(),
            "related_products": [product.to_dict() for product in self.related_products],
            "order_id": self.order_id,
            "channel": self.channel,
            "language": self.language,
            "metadata": self.metadata,
            "operational_context": (
                None if self.operational_context is None else self.operational_context.to_dict()
            ),
            "privacy_status": self.privacy_status,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> FeedbackRecord:
        source = SourceReference.from_dict(value["source"])
        expected_id = canonical_feedback_id(source.provider_id, source.source_record_id)
        feedback_id = str(value.get("feedback_id", expected_id))
        metadata = value.get("metadata", {})
        if not isinstance(metadata, dict):
            raise CanonicalRecordError("metadata must be an object")
        return cls(
            schema_version=str(value.get("schema_version", SCHEMA_VERSION)),
            feedback_id=feedback_id,
            source=source,
            original_text=str(value["original_text"]),
            title=_optional_string(value.get("title")),
            occurred_at=parse_utc_iso(str(value["occurred_at"])),
            rating=None if value.get("rating") is None else Rating.from_dict(value["rating"]),
            related_products=tuple(
                RelatedProduct.from_dict(item) for item in value.get("related_products", [])
            ),
            order_id=_optional_string(value.get("order_id")),
            channel=_optional_string(value.get("channel")),
            language=_optional_string(value.get("language")),
            metadata=metadata,
            operational_context=(
                None
                if value.get("operational_context") is None
                else OperationalContext.from_dict(value["operational_context"])
            ),
            privacy_status=str(value.get("privacy_status", "uninspected")),
        )


@dataclass(frozen=True, slots=True)
class DateRange:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise CanonicalRecordError("date range start must not be after its end")

    def to_dict(self) -> dict[str, JsonValue]:
        return {"start": utc_iso(self.start), "end": utc_iso(self.end)}


@dataclass(frozen=True, slots=True)
class DatasetMetadata:
    provider_id: str
    dataset_name: str
    dataset_version: str
    source_uri: str
    license: str
    attribution: str
    default_language: str | None
    record_count: int
    date_range: DateRange | None
    checksum_sha256: str
    imported_at: datetime | None = None
    schema_version: str = METADATA_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != METADATA_SCHEMA_VERSION:
            raise CanonicalRecordError(f"unsupported metadata version: {self.schema_version}")
        if self.record_count < 0:
            raise CanonicalRecordError("record_count cannot be negative")
        if len(self.checksum_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.checksum_sha256
        ):
            raise CanonicalRecordError("checksum_sha256 must be a lowercase SHA-256 digest")

    def mark_imported(self, timestamp: datetime | None = None) -> DatasetMetadata:
        return replace(self, imported_at=(timestamp or datetime.now(UTC)).astimezone(UTC))

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schema_version": self.schema_version,
            "provider_id": self.provider_id,
            "dataset_name": self.dataset_name,
            "dataset_version": self.dataset_version,
            "source_uri": self.source_uri,
            "license": self.license,
            "attribution": self.attribution,
            "default_language": self.default_language,
            "record_count": self.record_count,
            "date_range": None if self.date_range is None else self.date_range.to_dict(),
            "imported_at": None if self.imported_at is None else utc_iso(self.imported_at),
            "checksum_sha256": self.checksum_sha256,
        }


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    severity: IssueSeverity
    source_record_id: str | None = None
    source_file: str | None = None
    row_number: int | None = None
    blocking: bool = False

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "source_record_id": self.source_record_id,
            "source_file": self.source_file,
            "row_number": self.row_number,
            "blocking": self.blocking,
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    records_discovered: int
    valid_records: int
    rejected_records: int
    duplicate_records: int
    missing_text_records: int
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def warning_count(self) -> int:
        return sum(issue.severity is IssueSeverity.WARNING for issue in self.issues)

    @property
    def error_count(self) -> int:
        return sum(issue.severity is IssueSeverity.ERROR for issue in self.issues)

    @property
    def is_usable(self) -> bool:
        return self.valid_records > 0 and not any(issue.blocking for issue in self.issues)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "records_discovered": self.records_discovered,
            "valid_records": self.valid_records,
            "rejected_records": self.rejected_records,
            "duplicate_records": self.duplicate_records,
            "missing_text_records": self.missing_text_records,
            "warning_count": self.warning_count,
            "error_count": self.error_count,
            "is_usable": self.is_usable,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class DatasetLoadResult:
    records: tuple[FeedbackRecord, ...]
    metadata: DatasetMetadata
    validation: ValidationReport


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _optional_datetime(value: object) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    return parse_utc_iso(str(value))
