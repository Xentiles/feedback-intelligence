# Architecture

This document defines the repository's public architectural boundaries and
deliberate limits. Consequential decisions are recorded as ADRs.

![Recorded demo and optional processing runtime](assets/architecture.svg)

## Intended flow

```text
React → ASP.NET Core → PostgreSQL feedback + processing/outbox
                          ↓
                     Python worker
                  local PII redaction
                          ↓
                replaceable DecisionEngine
                fixture / SemIf / rules / LLM
                          ↓
               immutable decisions + provenance
                  per-dimension policy
                          ↓
                 idempotent projection
                          ↓
                ClickHouse signals → trends → API → React evidence views
```

OpenTelemetry observes the API-to-worker boundaries with sanitised metadata. Dataset
normalization, local privacy transformation, typed decisions, PostgreSQL workflow
persistence, the text-free ClickHouse projection boundary, and the read-only
dashboard → signal → evidence journey are implemented.

## Ownership

React presents the product and never holds model credentials or database access.
ASP.NET Core owns validation, API contracts, query orchestration, ingestion, and job
creation. The Python worker owns the privacy boundary, replaceable decision
adapters, confidence policy, retries, and decision provenance. Semantic model
judgments remain bounded; deterministic code owns arithmetic, time, aggregation,
workflow, and trend algorithms.

Runtime feature names are a versioned shared contract. The API binds decision
engine selection to an enum, while the worker uses typed decision and trend
registries. Configuration changes select registered implementations without
conditional workflow branches; unsupported values fail before work is accepted.
The trend registry includes the promoted `simple_rate_change` detector and an
evaluated `candidate_statistical` Beta-Binomial implementation. A generated metric
gate retains the simple detector because the candidate's mean delay is higher on the
shared synthetic back-test.

PostgreSQL is the canonical operational store. ClickHouse holds accepted derived
facts and aggregates. The projector uses stable event IDs, a PostgreSQL ledger, and
ClickHouse insert tokens rather than relying on eventual merges. Asynchronous work
uses PostgreSQL leases and an outbox; no separate broker is justified by the plan.

Shared wire definitions belong in `contracts/`. Versioned decision questions belong
in `schemas/feedback-decision/`. Data generation, reviewed evaluation labels, and
recorded decisions have separate ownership and provenance.

Dataset sources enter through a Python `DatasetProvider` boundary before any
privacy or decision boundary. The provider returns canonical feedback, dataset
provenance, and a validation report. Olist and mapped CSV schemas end at this
adapter; future processing sees only `feedback-record/1.0.0`. Operational context
is computed deterministically during normalization and stays distinct from later
semantic decisions. See [feedback datasets](data-sources.md).

The synthetic generator uses a versioned seed specification and writes canonical
feedback separately from scenario/event provenance. Exact regeneration verifies
the corpus while that separation prevents planted labels from entering model state.

`DecisionEngine` consumes only `ModelSafeFeedbackState`. The active manifest owns
fourteen typed question definitions; the SemIf adapter scores the declared options
with a pinned local open model, the System One Adapter sends equivalent typed
questions to a pinned structured-output LLM, the rule adapter applies bilingual
lexicons with fixed precedence, and the fixture adapter replays previously recorded
typed answers by redacted-input hash.
All produce the same body-free decision envelope. Confidence
policy remains a separate version axis and is intentionally uncalibrated.

Canonical records are still `uninspected`. `PrivacyBoundary` converts each one to
a distinct `ModelSafeFeedbackState` with an allow-listed decision serialization.
External engine adapters must consume that type, which makes passing a canonical
record directly a type-level architecture violation. Payment credentials stop at
the boundary; audit and telemetry representations omit both original and redacted
feedback bodies.

## Foundation choices

- Vite hosts the React dashboard; the plan does not require server-side rendering.
- Use npm for the single frontend package, a local .NET solution for the API and
  tests, and uv with a Python `src` package. No monorepo task framework is needed.
- Target Node.js 24, .NET 10 LTS, and Python 3.13. The .NET SDK version lives in
  `global.json`; dependency graphs are locked. See Microsoft's
  [.NET 10 downloads](https://dotnet.microsoft.com/en-us/download/dotnet/10.0) and
  [Vite runtime requirements](https://vite.dev/guide/).
- Use ESLint/Prettier/TypeScript, `dotnet format`, and Ruff/mypy/pytest for each
  stack's own quality checks.
- Keep Compose storage optional for the fixture-backed web/API demo. The `pipeline` profile gates
  its one-shot seed worker on real PostgreSQL and ClickHouse health checks. The
  `runtime` profile starts the continuous lease-based worker over the same stores.
- Infrastructure and Python runtime image tags follow a selected release line's
  patches. Dependency lockfiles pin application packages; image digests should be
  captured when publishing an evaluated release.
- Reserve schema version `1.0.0` as a folder with validated metadata. This small
  layout refinement supports later manifest/examples without defining the taxonomy.

## Current limits

The web and API expose read-only product data and typed trend results through
isolated fixture and live contexts. The worker owns a deterministic rate-change
detector and reproducible planted-incident back-test. ClickHouse exposes deduplicated
daily detector inputs partitioned by source and schema/model/policy cohort, but the
live view is empty because calibration has not produced accepted classifications.
HTTP ingestion and a continuous worker are available only in the opt-in local/private
runtime configuration. Ingestion requires a server-side API key and uses a bounded
fixed-window rate policy. W3C trace context is stored with the job and resumed by
the worker across redaction, decision, persistence, and projection spans. Trace
attributes and metric dimensions pass application and Collector allow-lists that
exclude content and credentials. There is no live trend scheduler or hosted
telemetry backend. Live evidence text remains restricted.

The [ADRs](adr/README.md) record accepted architecture decisions; they
do not imply that the corresponding features are implemented.
