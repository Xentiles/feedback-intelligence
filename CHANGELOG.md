# Changelog

The initial publication includes the privacy-boundary and CI repairs documented
in [the pre-publication security review](docs/quality/security-review.md).

## 0.2.0 — 2026-10-05

- Opt-in local upload workbench for CSV/XLSX/JSON/JSONL and pasted reviews.
- Versioned topic templates, explainable keywords, durable run history,
  exploratory analysis, evidence, matched-run comparison and CSV/JSON exports.
- Separate database principals, protected local sessions, encrypted credential
  vault, ChatGPT OAuth and explicitly selected OpenAI API billing.
- Dedicated deduplicated analytical projection and durable dataset purge.
- Deterministic 10,000-record rules scenario alongside the frozen showcase.
- Unified Orbital Clarity floating navigation, accessible inspectors and dialogs,
  populated filters, responsive UTC charts, automatic catalogs and reasoning effort.
- Isolated, admitted upload parsing with structure, timeout, memory and preview limits.
- Fixed pytest and optional model dependency overrides, with recorded compatibility.
- Existing owner-created ChatGPT samples verify two 25-record local configurations;
  they do not establish every model, human-gold quality or hosted readiness.
- Updated documentation and a verified local archive of development checkpoints.

### Compatibility and limits

No new database migration or contract version. Existing datasets/runs and frozen
benchmarks are preserved. Nested JSON cells, duplicate JSON keys and excessive
parser resources now produce explicit validation errors. Human calibration, hosted
authorization and legacy analytical follow-ups remain separate gates. Local
checkpoints are preserved outside public branches; v0.1.0 remains immutable.

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
