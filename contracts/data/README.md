# Canonical feedback data contract

Dataset adapters emit `feedback-record/1.0.0` documents. Downstream processing
depends on this contract and never on source table or column names.

The contract keeps four concerns separate:

- `source` identifies the provider, dataset version, and source record.
- `original_text`, rating, related products, and order/channel fields represent
  source facts without hidden translation.
- `operational_context` contains deterministic facts such as delivery timing and
  monetary totals. An AI model must not recalculate them.
- `privacy_status` is `uninspected` for every provider output. A separate privacy
  transformation must create model-safe input before any external decision call.

One feedback record can reference several products. Adapters must not duplicate a
review merely to make product relationships one-to-one.

The JSON Schemas are the language-neutral boundary. The Python models and provider
protocol live in `services/decision-worker`; future .NET or TypeScript consumers
should generate or implement equivalent types from these definitions.

`synthetic-seed-manifest.schema.json` defines the reproducibility manifest written
beside generated feedback. Scenario and planted-event attribution live in a separate
local provenance sidecar and are excluded from canonical feedback records.
