"""Deterministic scenario-based generator for canonical retail feedback."""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from feedback_intelligence_worker.data.models import (
    FeedbackRecord,
    Money,
    OperationalContext,
    Rating,
    RelatedProduct,
    SourceReference,
    canonical_feedback_id,
    utc_iso,
)
from feedback_intelligence_worker.synthetic.spec import (
    EventSpec,
    GeneratorSpec,
    ProductSpec,
    ScenarioSpec,
)

DATASET_NAME = "Feedback Intelligence deterministic synthetic retail feedback"
PROVENANCE_SCHEMA_VERSION = "synthetic-provenance/1.0.0"
MANIFEST_SCHEMA_VERSION = "synthetic-seed-manifest/1.0.0"


@dataclass(frozen=True, slots=True)
class SyntheticProvenance:
    feedback_id: str
    record_index: int
    source_type: str
    locale: str
    scenario_id: str
    synthetic_event_id: str | None
    product_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PROVENANCE_SCHEMA_VERSION,
            "feedback_id": self.feedback_id,
            "record_index": self.record_index,
            "source_type": self.source_type,
            "locale": self.locale,
            "scenario_id": self.scenario_id,
            "synthetic_event_id": self.synthetic_event_id,
            "product_ids": list(self.product_ids),
        }


@dataclass(frozen=True, slots=True)
class GeneratedSyntheticDataset:
    records: tuple[FeedbackRecord, ...]
    provenance: tuple[SyntheticProvenance, ...]
    manifest: dict[str, Any]

    def feedback_bytes(self) -> bytes:
        return _jsonl_bytes(record.to_dict() for record in self.records)

    def provenance_bytes(self) -> bytes:
        return _jsonl_bytes(item.to_dict() for item in self.provenance)

    def manifest_bytes(self) -> bytes:
        return (
            json.dumps(self.manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")


class SyntheticDatasetGenerator:
    """Generate canonical records from a fixed spec and isolated random seed."""

    def __init__(self, spec: GeneratorSpec) -> None:
        self._spec = spec
        self._products_by_id = {product.product_id: product for product in spec.products}
        self._scenarios_by_id = {scenario.scenario_id: scenario for scenario in spec.scenarios}

    def generate(
        self,
        *,
        seed: int | None = None,
        record_count: int | None = None,
    ) -> GeneratedSyntheticDataset:
        selected_seed = self._spec.default_seed if seed is None else seed
        selected_count = self._spec.default_record_count if record_count is None else record_count
        if selected_seed < 0:
            raise ValueError("seed must be non-negative")
        if selected_count < 1:
            raise ValueError("record_count must be positive")

        rng = random.Random(selected_seed)
        dataset_version = (
            f"{self._spec.generator_version}+seed.{selected_seed}"
            f"+config.{self._spec.checksum_sha256[:12]}"
        )
        records: list[FeedbackRecord] = []
        provenance: list[SyntheticProvenance] = []
        for index in range(selected_count):
            day_offset = (
                0
                if selected_count == 1
                else index * (self._spec.day_count - 1) // (selected_count - 1)
            )
            occurred_at = datetime.combine(
                self._spec.start_date + timedelta(days=day_offset),
                time.min,
                tzinfo=UTC,
            ) + timedelta(seconds=rng.randrange(86_400))
            event = self._select_event(rng, day_offset)
            scenario = (
                self._scenarios_by_id[event.scenario_id]
                if event is not None
                else _weighted_choice(
                    rng,
                    tuple((candidate, candidate.weight) for candidate in self._spec.scenarios),
                )
            )
            locale = _weighted_choice(rng, tuple(self._spec.locales.items()))
            primary_product = self._select_product(rng, scenario, event)
            related_products = self._related_products(rng, scenario, primary_product)
            days_value = self._days_value(rng, scenario)
            template = rng.choice(scenario.templates[locale])
            original_text = template.format(
                product=(primary_product.name if primary_product is not None else "product"),
                days=days_value,
            )
            rating_value = rng.choice(scenario.ratings)
            source_record_id = f"synthetic:{selected_seed}:{index:06d}"
            feedback_id = canonical_feedback_id("synthetic", source_record_id)
            operational_context = self._operational_context(
                rng,
                scenario,
                occurred_at,
                related_products,
                days_value,
            )
            record = FeedbackRecord(
                feedback_id=feedback_id,
                source=SourceReference(
                    provider_id="synthetic",
                    dataset_name=DATASET_NAME,
                    dataset_version=dataset_version,
                    source_record_id=source_record_id,
                ),
                original_text=original_text,
                occurred_at=occurred_at,
                rating=(
                    None
                    if rating_value is None
                    else Rating(Decimal(rating_value), Decimal(1), Decimal(5))
                ),
                related_products=related_products,
                order_id=(f"SYN-ORDER-{selected_seed}-{index:06d}" if scenario.has_order else None),
                channel=scenario.source,
                language=locale,
                metadata={},
                operational_context=operational_context,
            )
            records.append(record)
            provenance.append(
                SyntheticProvenance(
                    feedback_id=feedback_id,
                    record_index=index,
                    source_type=scenario.source,
                    locale=locale,
                    scenario_id=scenario.scenario_id,
                    synthetic_event_id=None if event is None else event.event_id,
                    product_ids=tuple(product.product_id for product in related_products),
                )
            )

        record_tuple = tuple(records)
        provenance_tuple = tuple(provenance)
        feedback_bytes = _jsonl_bytes(record.to_dict() for record in record_tuple)
        provenance_bytes = _jsonl_bytes(item.to_dict() for item in provenance_tuple)
        manifest = self._manifest(
            records=record_tuple,
            provenance=provenance_tuple,
            seed=selected_seed,
            feedback_bytes=feedback_bytes,
            provenance_bytes=provenance_bytes,
        )
        return GeneratedSyntheticDataset(record_tuple, provenance_tuple, manifest)

    def _select_event(self, rng: random.Random, day_offset: int) -> EventSpec | None:
        for event in self._spec.events:
            if event.active_on(day_offset) and rng.random() < event.record_share:
                return event
        return None

    def _select_product(
        self,
        rng: random.Random,
        scenario: ScenarioSpec,
        event: EventSpec | None,
    ) -> ProductSpec | None:
        if not scenario.has_product:
            return None
        if event is not None and event.product_id is not None:
            return self._products_by_id[event.product_id]
        return rng.choice(self._spec.products)

    def _related_products(
        self,
        rng: random.Random,
        scenario: ScenarioSpec,
        primary: ProductSpec | None,
    ) -> tuple[RelatedProduct, ...]:
        if primary is None:
            return ()
        selected = [primary]
        if scenario.has_order and rng.random() < 0.04:
            candidates = [product for product in self._spec.products if product != primary]
            selected.append(rng.choice(candidates))
        related: list[RelatedProduct] = []
        for position, product in enumerate(selected):
            quantity = 2 if position == 0 and rng.random() < 0.03 else 1
            freight = rng.choice((Decimal("0.00"), Decimal("4.99"), Decimal("7.99")))
            related.append(
                RelatedProduct(
                    product_id=product.product_id,
                    product_name=product.name,
                    category=product.category,
                    category_language="en",
                    quantity=quantity,
                    seller_ids=(f"synthetic-seller-{rng.randrange(1, 9):02d}",),
                    price=Money(product.price * quantity, "EUR"),
                    freight_cost=Money(freight, "EUR"),
                )
            )
        return tuple(related)

    def _days_value(self, rng: random.Random, scenario: ScenarioSpec) -> int:
        if scenario.scenario_id == "delivery_late":
            return rng.randint(3, 10)
        if scenario.scenario_id == "return_unresolved":
            return rng.randint(5, 20)
        return rng.randint(1, 4)

    def _operational_context(
        self,
        rng: random.Random,
        scenario: ScenarioSpec,
        occurred_at: datetime,
        products: tuple[RelatedProduct, ...],
        days_value: int,
    ) -> OperationalContext | None:
        if not scenario.has_order:
            return None
        delivered_at = occurred_at - timedelta(days=rng.randint(0, 7), hours=rng.randint(0, 12))
        if scenario.scenario_id == "delivery_late":
            delivery_delta = days_value
        elif scenario.scenario_id == "delivery_positive":
            delivery_delta = -rng.randint(1, 3)
        else:
            delivery_delta = rng.choice((-1, 0, 0, 0, 1))
        expected_at = delivered_at - timedelta(days=delivery_delta)
        purchased_at = min(delivered_at, expected_at) - timedelta(days=rng.randint(2, 8))
        total_price = sum(
            (product.price.amount for product in products if product.price is not None),
            Decimal("0"),
        )
        total_freight = sum(
            (
                product.freight_cost.amount
                for product in products
                if product.freight_cost is not None
            ),
            Decimal("0"),
        )
        seller_ids = {seller for product in products for seller in product.seller_ids}
        return OperationalContext(
            purchased_at=purchased_at,
            delivered_at=delivered_at,
            expected_delivery_at=expected_at,
            delivery_delta_days=float(delivery_delta),
            order_status=("returned" if scenario.source == "return_feedback" else "delivered"),
            total_price=Money(total_price, "EUR"),
            total_freight_cost=Money(total_freight, "EUR"),
            seller_count=len(seller_ids),
        )

    def _manifest(
        self,
        *,
        records: tuple[FeedbackRecord, ...],
        provenance: tuple[SyntheticProvenance, ...],
        seed: int,
        feedback_bytes: bytes,
        provenance_bytes: bytes,
    ) -> dict[str, Any]:
        source_counts = Counter(item.source_type for item in provenance)
        locale_counts = Counter(item.locale for item in provenance)
        scenario_counts = Counter(item.scenario_id for item in provenance)
        event_counts = Counter(
            item.synthetic_event_id for item in provenance if item.synthetic_event_id is not None
        )
        product_mentions = Counter(
            product_id for item in provenance for product_id in item.product_ids
        )
        dates = [record.occurred_at for record in records]
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "generator_version": self._spec.generator_version,
            "seed": seed,
            "record_count": len(records),
            "date_range": {
                "start": utc_iso(min(dates)),
                "end": utc_iso(max(dates)),
                "configured_days": self._spec.day_count,
            },
            "config_sha256": self._spec.checksum_sha256,
            "feedback_sha256": hashlib.sha256(feedback_bytes).hexdigest(),
            "provenance_sha256": hashlib.sha256(provenance_bytes).hexdigest(),
            "distributions": {
                "sources": dict(sorted(source_counts.items())),
                "locales": dict(sorted(locale_counts.items())),
                "scenarios": dict(sorted(scenario_counts.items())),
                "events": dict(sorted(event_counts.items())),
                "product_mentions": dict(sorted(product_mentions.items())),
            },
            "events": [
                {
                    "event_id": event.event_id,
                    "start_date": (
                        self._spec.start_date + timedelta(days=event.start_day)
                    ).isoformat(),
                    "end_date": (
                        None
                        if event.duration_days is None
                        else (
                            self._spec.start_date
                            + timedelta(days=event.start_day + event.duration_days - 1)
                        ).isoformat()
                    ),
                    "scenario_id": event.scenario_id,
                    "product_id": event.product_id,
                    "affected_records": event_counts[event.event_id],
                }
                for event in self._spec.events
            ],
            "provenance_separation": {
                "sidecar": "provenance.jsonl",
                "excluded_from_feedback_records": [
                    "scenario_id",
                    "synthetic_event_id",
                    "generator_expectations",
                ],
            },
        }


def write_generated_dataset(
    dataset: GeneratedSyntheticDataset,
    output_directory: Path,
    *,
    force: bool = False,
) -> tuple[Path, Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    feedback_path = output_directory / "feedback.jsonl"
    provenance_path = output_directory / "provenance.jsonl"
    manifest_path = output_directory / "seed-manifest.json"
    destinations = (feedback_path, provenance_path, manifest_path)
    existing = [path for path in destinations if path.exists()]
    if existing and not force:
        names = ", ".join(path.name for path in existing)
        raise FileExistsError(f"Generated files already exist ({names}); pass --force to replace")
    payloads = (
        dataset.feedback_bytes(),
        dataset.provenance_bytes(),
        dataset.manifest_bytes(),
    )
    temporary_paths = tuple(path.with_suffix(path.suffix + ".tmp") for path in destinations)
    try:
        for temporary, payload in zip(temporary_paths, payloads, strict=True):
            temporary.write_bytes(payload)
        for temporary, destination in zip(temporary_paths, destinations, strict=True):
            temporary.replace(destination)
    finally:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)
    return destinations


def _weighted_choice[T](rng: random.Random, choices: tuple[tuple[T, int], ...]) -> T:
    total = sum(weight for _, weight in choices)
    selected = rng.randrange(total)
    cumulative = 0
    for value, weight in choices:
        cumulative += weight
        if selected < cumulative:
            return value
    raise RuntimeError("weighted selection failed")


def _jsonl_bytes(values: Iterable[dict[str, Any]]) -> bytes:
    lines = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for value in values
    )
    return ("\n".join(lines) + "\n").encode("utf-8")
