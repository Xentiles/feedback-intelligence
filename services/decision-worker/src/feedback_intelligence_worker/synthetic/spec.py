"""Validated, versioned configuration for deterministic synthetic generation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

import yaml

SUPPORTED_SOURCES = {
    "product_review",
    "support_ticket",
    "delivery_survey",
    "return_feedback",
    "site_feedback",
}


class GeneratorSpecError(ValueError):
    """Raised when the versioned generator specification is invalid."""


@dataclass(frozen=True, slots=True)
class ProductSpec:
    product_id: str
    name: str
    category: str
    price: Decimal


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    scenario_id: str
    source: str
    weight: int
    has_product: bool
    has_order: bool
    ratings: tuple[int | None, ...]
    templates: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class EventSpec:
    event_id: str
    start_day: int
    duration_days: int | None
    scenario_id: str
    product_id: str | None
    record_share: float

    def active_on(self, day_offset: int) -> bool:
        if day_offset < self.start_day:
            return False
        return self.duration_days is None or day_offset < self.start_day + self.duration_days


@dataclass(frozen=True, slots=True)
class GeneratorSpec:
    generator_version: str
    default_seed: int
    default_record_count: int
    start_date: date
    day_count: int
    locales: dict[str, int]
    products: tuple[ProductSpec, ...]
    scenarios: tuple[ScenarioSpec, ...]
    events: tuple[EventSpec, ...]
    checksum_sha256: str


def load_generator_spec(path: Path) -> GeneratorSpec:
    if not path.is_file():
        raise GeneratorSpecError(f"Generator specification does not exist: {path}")
    source_bytes = path.read_bytes()
    try:
        payload = yaml.safe_load(source_bytes)
    except yaml.YAMLError as error:
        raise GeneratorSpecError(f"Invalid generator YAML: {error}") from error
    if not isinstance(payload, dict):
        raise GeneratorSpecError("Generator specification must be an object")
    if payload.get("version") != 1:
        raise GeneratorSpecError("Only generator specification version 1 is supported")

    generator_version = _required_text(payload, "generator_version")
    default_seed = _positive_int(payload, "default_seed", allow_zero=True)
    default_record_count = _positive_int(payload, "default_record_count")
    day_count = _positive_int(payload, "day_count")
    if day_count < 365:
        raise GeneratorSpecError("day_count must cover at least 365 days")
    try:
        start = date.fromisoformat(_required_text(payload, "start_date"))
    except ValueError as error:
        raise GeneratorSpecError("start_date must be an ISO calendar date") from error

    locales = _weighted_mapping(payload.get("locales"), "locales")
    products = _products(payload.get("products"))
    scenarios = _scenarios(payload.get("scenarios"), set(locales))
    events = _events(
        payload.get("events"),
        scenario_ids={scenario.scenario_id for scenario in scenarios},
        product_ids={product.product_id for product in products},
        day_count=day_count,
    )
    return GeneratorSpec(
        generator_version=generator_version,
        default_seed=default_seed,
        default_record_count=default_record_count,
        start_date=start,
        day_count=day_count,
        locales=locales,
        products=products,
        scenarios=scenarios,
        events=events,
        checksum_sha256=hashlib.sha256(source_bytes).hexdigest(),
    )


def _products(value: object) -> tuple[ProductSpec, ...]:
    rows = _object_list(value, "products")
    products: list[ProductSpec] = []
    seen: set[str] = set()
    for row in rows:
        product_id = _required_text(row, "id")
        if product_id in seen:
            raise GeneratorSpecError(f"Duplicate product id: {product_id}")
        seen.add(product_id)
        try:
            price = Decimal(_required_text(row, "price"))
        except InvalidOperation as error:
            raise GeneratorSpecError(f"Invalid price for product {product_id}") from error
        if price <= 0:
            raise GeneratorSpecError(f"Product price must be positive: {product_id}")
        products.append(
            ProductSpec(
                product_id=product_id,
                name=_required_text(row, "name"),
                category=_required_text(row, "category"),
                price=price,
            )
        )
    if not products:
        raise GeneratorSpecError("At least one product is required")
    return tuple(products)


def _scenarios(value: object, locales: set[str]) -> tuple[ScenarioSpec, ...]:
    rows = _object_list(value, "scenarios")
    scenarios: list[ScenarioSpec] = []
    seen: set[str] = set()
    for row in rows:
        scenario_id = _required_text(row, "id")
        if scenario_id in seen:
            raise GeneratorSpecError(f"Duplicate scenario id: {scenario_id}")
        seen.add(scenario_id)
        source = _required_text(row, "source")
        if source not in SUPPORTED_SOURCES:
            raise GeneratorSpecError(f"Unsupported source for {scenario_id}: {source}")
        ratings_value = row.get("ratings")
        if not isinstance(ratings_value, list) or not ratings_value:
            raise GeneratorSpecError(f"Scenario ratings must be a non-empty list: {scenario_id}")
        ratings: list[int | None] = []
        for rating in ratings_value:
            if rating is None:
                ratings.append(None)
            elif isinstance(rating, int) and not isinstance(rating, bool) and 1 <= rating <= 5:
                ratings.append(rating)
            else:
                raise GeneratorSpecError(f"Scenario rating must be null or 1-5: {scenario_id}")
        templates_value = row.get("templates")
        if not isinstance(templates_value, dict) or set(templates_value) != locales:
            raise GeneratorSpecError(
                f"Scenario templates must define exactly {sorted(locales)}: {scenario_id}"
            )
        templates: dict[str, tuple[str, ...]] = {}
        for locale, locale_templates in templates_value.items():
            if not isinstance(locale, str) or not isinstance(locale_templates, list):
                raise GeneratorSpecError(f"Invalid templates for scenario: {scenario_id}")
            cleaned = tuple(str(template).strip() for template in locale_templates)
            if not cleaned or any(not template for template in cleaned):
                raise GeneratorSpecError(f"Templates cannot be blank: {scenario_id}/{locale}")
            templates[locale] = cleaned
        has_product = _required_bool(row, "has_product")
        has_order = _required_bool(row, "has_order")
        if has_order and not has_product:
            raise GeneratorSpecError(f"Order scenario must have a product: {scenario_id}")
        scenarios.append(
            ScenarioSpec(
                scenario_id=scenario_id,
                source=source,
                weight=_positive_int(row, "weight"),
                has_product=has_product,
                has_order=has_order,
                ratings=tuple(ratings),
                templates=templates,
            )
        )
    if {scenario.source for scenario in scenarios} != SUPPORTED_SOURCES:
        missing = sorted(SUPPORTED_SOURCES - {scenario.source for scenario in scenarios})
        raise GeneratorSpecError(f"Scenarios do not cover every source type: {missing}")
    return tuple(scenarios)


def _events(
    value: object,
    *,
    scenario_ids: set[str],
    product_ids: set[str],
    day_count: int,
) -> tuple[EventSpec, ...]:
    rows = _object_list(value, "events")
    events: list[EventSpec] = []
    seen: set[str] = set()
    for row in rows:
        event_id = _required_text(row, "id")
        if event_id in seen:
            raise GeneratorSpecError(f"Duplicate event id: {event_id}")
        seen.add(event_id)
        start_day = _positive_int(row, "start_day", allow_zero=True)
        if start_day >= day_count:
            raise GeneratorSpecError(f"Event begins outside generated range: {event_id}")
        duration_value = row.get("duration_days")
        duration = None
        if duration_value is not None:
            if not isinstance(duration_value, int) or isinstance(duration_value, bool):
                raise GeneratorSpecError(f"Invalid event duration: {event_id}")
            duration = duration_value
            if duration <= 0 or start_day + duration > day_count:
                raise GeneratorSpecError(f"Event duration exceeds generated range: {event_id}")
        scenario_id = _required_text(row, "scenario_id")
        if scenario_id not in scenario_ids:
            raise GeneratorSpecError(f"Unknown event scenario: {event_id}/{scenario_id}")
        product_id = _optional_text(row.get("product_id"))
        if product_id is not None and product_id not in product_ids:
            raise GeneratorSpecError(f"Unknown event product: {event_id}/{product_id}")
        share_value = row.get("record_share")
        if not isinstance(share_value, (int, float)) or isinstance(share_value, bool):
            raise GeneratorSpecError(f"Invalid record_share: {event_id}")
        share = float(share_value)
        if not 0 < share <= 1:
            raise GeneratorSpecError(f"record_share must be within (0, 1]: {event_id}")
        events.append(
            EventSpec(
                event_id=event_id,
                start_day=start_day,
                duration_days=duration,
                scenario_id=scenario_id,
                product_id=product_id,
                record_share=share,
            )
        )
    if not events:
        raise GeneratorSpecError("At least one planted event is required")
    return tuple(events)


def _weighted_mapping(value: object, label: str) -> dict[str, int]:
    if not isinstance(value, dict) or not value:
        raise GeneratorSpecError(f"{label} must be a non-empty object")
    result: dict[str, int] = {}
    for key, weight in value.items():
        if not isinstance(key, str) or not key.strip():
            raise GeneratorSpecError(f"{label} keys must be non-blank strings")
        if not isinstance(weight, int) or isinstance(weight, bool) or weight <= 0:
            raise GeneratorSpecError(f"{label} weights must be positive integers")
        result[key] = weight
    return result


def _object_list(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise GeneratorSpecError(f"{label} must be a list")
    if not all(isinstance(item, dict) for item in value):
        raise GeneratorSpecError(f"Every {label} entry must be an object")
    return cast(list[dict[str, Any]], value)


def _required_text(value: dict[str, Any], key: str) -> str:
    raw = value.get(key)
    if raw is None:
        raise GeneratorSpecError(f"Missing required field: {key}")
    cleaned = str(raw).strip()
    if not cleaned:
        raise GeneratorSpecError(f"Field cannot be blank: {key}")
    return cleaned


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _positive_int(value: dict[str, Any], key: str, *, allow_zero: bool = False) -> int:
    raw = value.get(key)
    minimum = 0 if allow_zero else 1
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < minimum:
        qualifier = "non-negative" if allow_zero else "positive"
        raise GeneratorSpecError(f"{key} must be a {qualifier} integer")
    return raw


def _required_bool(value: dict[str, Any], key: str) -> bool:
    raw = value.get(key)
    if not isinstance(raw, bool):
        raise GeneratorSpecError(f"{key} must be a boolean")
    return raw
