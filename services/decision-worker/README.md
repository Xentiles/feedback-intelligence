# Feedback Intelligence decision worker

This directory contains the executable Python data, privacy, and decision boundary
for Feedback Intelligence. It provides canonical import, synthetic generation,
recorded decisions, local SemIf, a structured-output LLM baseline, deterministic rules,
PostgreSQL workflow persistence, ClickHouse projection CLIs, and a continuous
lease-based worker entry point.

Python 3.13 is the baseline. The package uses a `src` layout and exposes
`decision-worker`, `feedback-data`, `feedback-synthetic`, `feedback-privacy`,
`feedback-decisions`, `feedback-evaluation`, `feedback-trends`, and `feedback-storage`.

Runtime selection is typed. `DECISION_ENGINE` resolves `fixture`, `semif`, `rules`,
or `llm` through the decision registry. `TREND_ALGORITHM` resolves
`simple_rate_change` or `candidate_statistical` through the detector registry.
Unknown names fail before a job or evaluation runs.

## Local setup

Install the exact locked development environment:

```bash
uv sync --locked
```

Run the entry point:

```bash
uv run --locked decision-worker
```

Show command help:

```bash
uv run --locked decision-worker --help
```

Validate and profile the committed demo dataset:

```bash
uv run --locked feedback-data validate synthetic
uv run --locked feedback-data profile synthetic
```

Generate and exactly verify the ignored 10,000-record synthetic corpus:

```bash
uv run --locked feedback-synthetic generate
uv run --locked feedback-synthetic verify
uv run --locked feedback-data validate synthetic \
  --path ../../data/synthetic/generated/feedback.jsonl
```

The versioned YAML controls products, weighted English and Swedish scenarios, and
four temporal change events. The seed manifest records configuration and artifact
checksums. Scenario and event attribution is isolated in `provenance.jsonl`; it is
never added to canonical records or model input.

Exercise the local pre-provider privacy boundary:

```bash
uv run --locked feedback-privacy synthetic
uv run --locked feedback-privacy olist --json
```

`feedback-privacy` makes no external calls and never prints feedback bodies. It
produces a minimal model-state shape in memory, redacts supported PII patterns,
and rejects likely payment credentials. Detection guarantees and limitations are
documented in [the privacy guide](../../docs/privacy.md).

Replay the committed SemIf outputs without credentials:

```bash
uv run --locked feedback-decisions synthetic --json
```

Run the local rule baseline without credentials:

```bash
uv run --locked feedback-decisions synthetic --engine rules --force --json
```

Local SemIf mode pins the code and Qwen model revisions and must be selected
explicitly. On an Apple Silicon host:

```bash
uv sync --locked --extra semif
uv run --locked --extra semif feedback-decisions \
  synthetic --engine semif --limit 1 --force --json
```

The schema, adapter behavior, envelope boundary, and fixture refresh command are
documented in [the decision-engine guide](../../docs/decision-engine.md).

Run the pinned general-purpose LLM baseline through the same typed question
objects and evaluation writer after setting `OPENAI_API_KEY` in the ignored `.env`:

```bash
docker compose --profile worker run --rm --build \
  --entrypoint feedback-evaluation decision-worker \
  predict --engine llm --limit 1 \
  --output /app/data/processed/evaluation/gpt-5.4-mini-2026-03-17.jsonl \
  --force --json
```

This path pins `gpt-5.4-mini-2026-03-17`, requests probability-mode structured
outputs through `system-one-adapter==0.2.0`, and records cumulative retry token
usage. The checked-in experiment was deliberately closed after 192 of 480
successful records. It consumed 477,777 billed tokens for an owner-confirmed
$0.39; a linear 480-record estimate is approximately $0.98. Adapter counters are retained as
diagnostic telemetry and are not treated as billing totals.

Rebuild the frozen annotation sample from the verified synthetic corpus and check
human-label readiness:

```bash
uv run --locked feedback-evaluation sample --force --json
uv run --locked feedback-evaluation readiness --json
uv run --locked feedback-evaluation report --json
```

Readiness currently exits 1 by design: the 480-record template is frozen but has
not been human annotated. The aggregation policy therefore has null thresholds and
cannot route answers into aggregates.

Once a split is complete, `feedback-evaluation score` validates a provider-neutral
prediction JSONL file and generates machine-readable and Markdown reports. It
computes primitive-specific quality, calibration, selective-coverage, language,
latency, token/cost, and failure metrics. Locked-test scoring requires the explicit
`--unlock-locked-test` flag.

Run pinned SemIf over the frozen evaluation records locally:

```bash
uv run --locked --extra semif feedback-evaluation predict \
  --engine semif \
  --dataset ../../evaluation/ai-reference/feedback-decision-1.0.0 \
  --output /tmp/semif.predictions.jsonl --force --json
```

The command checkpoints one text-free prediction row per record and supports
`--resume`. The checked-in 480-record output is compared with the explicitly
non-human Sol-medium reference; CI only re-scores the frozen output and does not
load model weights.

Reproduce both detector-only synthetic evaluations and the promotion gate:

```bash
uv run --locked feedback-trends evaluate --algorithm simple_rate_change
uv run --locked feedback-trends evaluate --algorithm candidate_statistical
uv run --locked feedback-trends compare
```

The commands use frozen 7-day current and previous 28-day baseline windows, keep
planted-event truth out of detector inputs, and rewrite all checked-in reports
byte-for-byte. The candidate improves precision and false-alert rate but increases
mean delay, so the generated gate retains the simple detector. Measurements and
limitations are documented in [the trend evaluation](../../evaluation/trends/README.md).

With local PostgreSQL and ClickHouse passwords set in the ignored root `.env`, run
the idempotent persistent demo from the repository root:

```bash
docker compose --profile pipeline up --build \
  --abort-on-container-exit --exit-code-from pipeline-worker pipeline-worker
```

The command persists nine immutable decisions and 126 answers, drains nine outbox
events, and is safe to repeat. Because policy calibration is pending, all events are
recorded as skipped and no ClickHouse signal fact becomes aggregate-eligible. See
[storage and projection](../../docs/storage-and-projection.md).

The `olist` provider can fetch, validate, profile, and import the reference Kaggle
dataset. The `csv` provider maps a user export through a versioned YAML file. Both
emit the same `feedback-record/1.0.0` contract and mark data as `uninspected`.
Complete commands, Olist joins, validation behavior, and the provider extension
guide are in [the repository data guide](../../docs/data-sources.md).

Run the same checks expected in CI:

```bash
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src tests
uv run --locked pytest
```

Build and run the container from the repository root:

```bash
docker build -f services/decision-worker/Dockerfile \
  -t feedback-intelligence-decision-worker .
docker run --rm feedback-intelligence-decision-worker

docker compose --profile worker run --rm --entrypoint feedback-data \
  decision-worker profile synthetic

docker compose --profile worker run --rm --entrypoint feedback-synthetic \
  decision-worker generate --count 100 --output /tmp/generated

# With storage credentials configured, consume API-created jobs continuously
docker compose --profile runtime up -d --build processing-worker
```

Set `OTEL_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT` to export content-free
`feedback.process`, `feedback.redact`, `decision.evaluate`, `decision.persist`, and
`analytics.project` spans plus decision/projection metrics. The worker resumes the
W3C context stored by the API. Trace IDs can identify workflow records, while metric
labels deliberately exclude record IDs. The local Collector applies a second
attribute allow-list before export.

## Planned worker boundary

The remaining worker behavior will be added in vertical slices. It will eventually
own:

- broader evaluated PII detection and restricted persistence beyond the current
  deterministic redaction baseline and canary tests;
- fitted thresholds for the existing per-question confidence-policy framework,
  preserving review and abstention;
- queue-age, retry, and projection-lag telemetry beyond the implemented
  cross-service decision/projection spans and outcome metrics;
- reproducible evaluation across providers, model/schema/policy versions, language slices, quality,
  calibration, latency, and cost.

Calibrated thresholds, a completed 480-record LLM benchmark, full hosted-mode controls,
and completed human labels are absent. The HTTP ingestion boundary and continuous
job/outbox loop are implemented over the existing leases and retries. The frozen decision schema,
SemIf and LLM adapters, fixture engine, deterministic annotation sample, shared
scorer, policy gate, persistent workflow, text-free analytical model, dataset
configuration, and privacy boundary are implemented independently.

Raw feedback must remain in the restricted operational boundary. External decision providers receive
only redacted state, and analytics receive derived decisions without unredacted text. Arithmetic,
aggregation, date handling, and trend detection stay in deterministic application code rather than the
model adapter.
