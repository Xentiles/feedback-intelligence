# Changelog

The initial publication includes the privacy-boundary and CI repairs documented
in [the pre-publication security review](docs/quality/security-review.md).

## 0.1.0 — 2026-09-20

### Available

- No-key Docker demo with 480 synthetic records and interchangeable SemIf, rules,
  and Sol-medium decision sources.
- Responsive dashboard, collapsible navigation, monthly descriptive charts,
  signal exploration, source evidence, and immutable decision provenance.
- PostgreSQL jobs/outbox, privacy transformation, typed decision adapters,
  retry-safe detector inputs, and opt-in local ingestion and telemetry.
- Frozen AI-reference comparisons and planted-incident detector evaluations.
- Screenshot walkthrough, model card, architecture visual, generated benchmark,
  and CI publication-path checks.

### Known limits

Human-gold labels and calibrated confidence policies remain incomplete. Demo
eligibility is illustrative. The GPT-5.4 Mini experiment is closed at 192 successful
records; it is not a complete 480-record comparison. Live hosting needs additional
authorization, credential separation, and retention controls. See
[release readiness](docs/release-readiness.md) and [model card](MODEL_CARD.md).

The tagged source-release commit passed all six remote CI jobs after correcting
Linux report serialization, container readiness retries and stale rules-report
metadata. The workflow uses Node 24 Actions and Ubuntu 24.04 runners. No paid
inference was run.

This is a source-only GitHub release. It does not include binaries, container
images, model weights, private planning material, or external raw data.
