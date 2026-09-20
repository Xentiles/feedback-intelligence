# Feedback datasets

The data layer converts replaceable source datasets into
`feedback-record/1.0.0`. Downstream code consumes that contract rather than a
Kaggle table, CSV column, or provider-specific object. Import, profiling, and
validation are deterministic and make no AI calls.

## Supported providers

| Provider | Purpose | Setup | Current normalization level |
| --- | --- | --- | --- |
| `synthetic` | Committed demo or generated development corpus | None | Canonical records with varied Level A-C context |
| `olist` | Reference multi-table public dataset | Kaggle download or manual CSV placement | Level C, including orders, products, sellers, delivery, and money |
| `csv` | Small user-supplied flat export | CSV plus a versioned YAML mapping | Level A or B, depending on mapped product/order fields |

Select the default with `FEEDBACK_DATA_PROVIDER=synthetic|olist|csv`. A command's
explicit provider takes precedence. `FEEDBACK_DATA_PATH` overrides the default
synthetic file or Olist directory; the CSV provider instead requires `--file` and
`--mapping`.

The normalization levels describe available context, not data quality:

- **Level A:** feedback identity, original text, occurrence time, and optional
  title/rating/language/channel.
- **Level B:** Level A plus direct product or order references.
- **Level C:** Level B plus joined operational facts such as item quantities,
  sellers, monetary totals, and delivery timing.

## Deterministic synthetic corpus

The versioned `data/synthetic/generator-v1.yaml` specification produces 10,000
records by default. A local random generator uses only the recorded integer seed;
there are no network or AI calls. The records span 450 days and cover five source
types, twelve retail products, sixteen bilingual scenarios, mixed and ambiguous
feedback, spelling errors, terse responses, English/Swedish code-switching,
sarcasm-like phrasing, irrelevant chatter, missing ratings, and four known change
events.

Generator-only attribution is written to `provenance.jsonl`, keyed by the canonical
feedback UUID. It includes scenario and planted-event identifiers for later trend
evaluation. Those identifiers are absent from `feedback.jsonl` and the privacy
boundary's allow-listed model state, preventing answer leakage into classification.
The adjacent seed manifest records exact SHA-256 checksums and distributions.

## Canonical contract

The language-neutral schemas are
[`feedback-record.schema.json`](../contracts/data/feedback-record.schema.json) and
[`dataset-metadata.schema.json`](../contracts/data/dataset-metadata.schema.json).
Every feedback record includes a stable UUID derived from provider and source ID,
source provenance, original text, an offset-aware UTC timestamp, related products,
and `privacy_status: uninspected`. Ratings carry their original scale. Money uses
decimal strings and an ISO-style currency code to avoid binary floating-point
rounding.

`operational_context` is separate from feedback text and future AI decisions.
Adapters compute dates, totals, quantities, and seller counts in code. Dataset
sidecars record provider, source version, attribution, license, source checksum,
record count, date range, and import time.

## Olist reference adapter

The adapter reads the **Brazilian E-Commerce Public Dataset by Olist** from Kaggle
handle `olistbr/brazilian-ecommerce`. Olist lists the dataset under
**CC BY-NC-SA 4.0**. Its data is not copied into this repository, and its license
does not change the repository source-code license. Preserve this attribution:
“Olist, Brazilian E-Commerce Public Dataset.”

The raw files join as follows:

| Source | Key | Canonical use |
| --- | --- | --- |
| `olist_order_reviews_dataset.csv` | `review_id`, `order_id` | One feedback record, original title/body, 1–5 rating, review creation time |
| `olist_orders_dataset.csv` | `order_id` | Order status, purchase/delivery/estimated timestamps |
| `olist_order_items_dataset.csv` | `order_id`, `product_id`, `seller_id` | Product quantity, seller IDs, price and freight totals |
| `olist_products_dataset.csv` | `product_id` | Portuguese product category |
| `product_category_name_translation.csv` | Portuguese category | Optional English category translation |

One review always remains one feedback record. For an order containing several
products, `related_products[]` contains one entry per product. Repeated line items
for that product increase `quantity`; seller IDs are deduplicated and sorted;
price and freight are summed. Order totals and distinct seller count appear once
in `operational_context`. This avoids inflating review counts while retaining the
one-to-many relationship.

Olist timestamps have no offset. The adapter documents and applies
`America/Sao_Paulo`, then serializes UTC. `delivery_delta_days` is actual delivery
minus estimated delivery: positive is late, negative is early. Categories use the
English translation when the optional table contains one; otherwise the original
Portuguese value and `pt-BR` language tag are retained. Review text remains in
Portuguese and is never auto-translated. A missing body falls back to a present
title with a warning; a review with neither is rejected.

Required joins, UTF-8 input, table schemas, unique lookup keys, source IDs,
timestamps, rating range, and duplicate reviews are validated. Missing optional
translation, malformed optional operational dates, missing product metadata, and
invalid monetary cells generate explicit warnings. Invalid feedback rows are
counted and reported rather than silently coerced.

Olist reviews are written at order level, so the data cannot reliably attribute a
sentence to one item in a multi-product order. It has no product display names,
support-case outcomes, explicit return outcomes, or per-review language labels.
The adapter therefore leaves product names empty, keeps every related product,
uses the dataset's documented Portuguese context as `pt-BR`, and makes no claims
about support or returns. Rating-only rows without title or body are reported and
rejected because the canonical contract represents textual feedback.

## Commands

From `services/decision-worker`:

```sh
# The committed demo requires no download or credentials.
uv run --locked feedback-data validate synthetic
uv run --locked feedback-data profile synthetic

# Build and verify the full ignored synthetic corpus.
uv run --locked feedback-synthetic generate
uv run --locked feedback-synthetic verify
uv run --locked feedback-data profile synthetic \
  --path ../../data/synthetic/generated/feedback.jsonl

# Download into the ignored data/external/olist/raw directory.
uv run --locked feedback-data fetch olist
uv run --locked feedback-data validate olist
uv run --locked feedback-data profile olist
uv run --locked feedback-data import olist

# Machine-readable output is available for validate/profile/import.
uv run --locked feedback-data profile olist --json
```

KaggleHub can use an existing Kaggle login or credentials supported by the Kaggle
SDK. Keep credentials outside the repository. If download is unavailable, extract
the source CSVs manually into `data/external/olist/raw/` and run validation.

Compose mounts the repository `data/` directory into the worker container:

```sh
docker compose --profile worker run --rm --build \
  --entrypoint feedback-data decision-worker profile synthetic
```

Normalized imports go to `data/processed/<provider>/feedback.jsonl` with adjacent
`.metadata.json` and `.validation.json` sidecars. Raw and processed data are both
Git-ignored and excluded from build contexts.

## User-supplied CSV

Inspect headers and a small sample first; samples can contain sensitive source
values:

```sh
uv run --locked feedback-data inspect /path/to/feedback.csv --sample 3
uv run --locked feedback-data validate csv \
  --file /path/to/feedback.csv \
  --mapping ../../data/fixtures/mappings/example-csv.yaml
uv run --locked feedback-data import csv \
  --file /path/to/feedback.csv \
  --mapping /path/to/mapping.yaml
```

Mapping version 1 requires `id`, `text`, and `timestamp`. It supports `title`,
`rating`, `product_id`, `product_name`, `category`, and `order_id`, plus dataset
name/version, attribution, license, language, channel, timezone, and rating scale.
Naive timestamps use the mapping timezone; timestamps with offsets keep their
instant and normalize to UTC. Ambiguous/nonexistent local times during a daylight
saving transition are rejected; supply an explicit offset. Malformed rows are
reported with logical CSV record positions (header is row 1), including records
after a malformed row; the count is not a physical line number for quoted multiline
fields. Missing product, rating, language and operational fields are not invented.

A minimal repository-owned CSV and mapping are available at
[`data/examples/custom-feedback.csv`](../data/examples/custom-feedback.csv) and
[`custom-feedback.mapping.yaml`](../data/examples/custom-feedback.mapping.yaml).
They validate/import as two records through the same `csv` CLI without external
data or credentials. The fuller example mapping is
[`data/fixtures/mappings/example-csv.yaml`](../data/fixtures/mappings/example-csv.yaml).
People supplying data are responsible for permission, licensing, retention, and
appropriate handling of personal information in that source.

## Adding a provider

Implement the `DatasetProvider` protocol in
`services/decision-worker/src/feedback_intelligence_worker/data/provider.py`:

```python
class DatasetProvider(Protocol):
    provider_id: str

    def metadata(self) -> DatasetMetadata: ...
    def validate_source(self) -> ValidationReport: ...
    def load_feedback(self) -> DatasetLoadResult: ...
```

The adapter should validate its source before constructing records, use stable
source identifiers, normalize timestamps explicitly, preserve original text and
language, expose licensing/provenance, and emit only `uninspected` records. Register
it in `data/config.py`, add focused fixtures for valid and malformed cases, and add
the provider to `SUPPORTED_PROVIDERS`. Provider-specific columns must not escape
through the canonical model.

## Privacy boundary

Normalization is not redaction. Imported records can contain personal data from
their source and therefore retain `privacy_status: uninspected`. Do not send them
to external AI providers, logs, traces, or analytical storage. The worker's local
`PrivacyBoundary` produces a separate model-safe representation and passes canary
tests for its documented rules. It remains a deterministic baseline with explicit
limitations; source-specific minimisation and evaluated detection are still needed
for arbitrary private data. See [privacy boundaries](privacy.md).
