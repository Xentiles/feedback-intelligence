# ClickHouse analytical store

Migration `001_analytics_model.sql` creates text-free `signal_facts`, daily signal
rollups, and daily topic rollups. Migration `002_trend_inputs.sql` adds canonical
provider/dataset/version identity, immutable decision time, explicit nullable
accepted-positive classifications, and the `daily_detector_inputs` view used by
the trend engine.
Eligibility is stored per decision dimension so a future calibrated policy can
accept one signal while routing another for review.

The current policy is uncalibrated, so the projector records completion in the
PostgreSQL projection ledger and deliberately skips ClickHouse insertion. This
keeps unreviewed model output out of analytical facts. Once an active policy exists,
eligible fields can enter `signal_facts` using the versioned projection event.

`daily_detector_inputs` is the safe source for future rate detection. It explicitly
deduplicates projection retries by `projection_id`, then selects the latest immutable
decision for each feedback item inside a provider, dataset, dataset version, schema,
model, and policy cohort. Those cohort keys remain in every aggregate group, so
incompatible provenance cannot be combined accidentally. Product, channel, and
locale dimensions are retained for downstream slicing.

The view emits integer `eligible_feedback` denominators and integer
`accepted_positive` numerators. It requires an active, versioned policy, an eligible
dimension, and a non-null explicit accepted-positive classification. It never turns
a probability sum or an arbitrary probability threshold into a classification.
The current producer emits all eligibility flags as false and all accepted-positive
values as null, so the view is intentionally empty until calibrated routing is
implemented. The older `daily_signal_rollup` and `daily_topic_rollup` tables remain
available for compatibility, but they are not the source of truth for trend input.

The isolated 2026-09-20 audit demonstrated why: replaying one accepted synthetic
test fact with the same insert token kept one effective fact and one detector
denominator, but the legacy materialized rollup denominator became two. A replay
with a different token made that legacy denominator three while the detector view
still returned one. Do not use these legacy tables for dashboard metrics; retire
or replace them before exposing any new aggregate surface. Reproduce with
`scripts/quality_projection_check.py`, which creates and removes its own database.

Projection IDs and insert-deduplication tokens are deterministic. The MergeTree
deduplication window protects ambiguous network retries, while application-level
outbox identity and the PostgreSQL ledger remain the primary idempotency controls.
No original or redacted feedback text exists in this schema.
