# Feedback Intelligence API

ASP.NET Core .NET 10 API for Feedback Intelligence. It preserves the standard health endpoint, exposes a versioned read journey from metadata to immutable evidence, and provides an opt-in feedback ingestion boundary for private/local runtimes.

Every dashboard request requires an explicit `context=demo|live` value. The demo
context can select committed 480-record SemIf, rules-baseline, or Sol-medium reference
fixtures in `src/FeedbackIntelligence.Api/Fixtures`; it never writes to either store.
Each fixture preserves the matching deterministic synthetic source dates, products,
categories, languages, and channels. Sol remains explicitly illustrative and not
human gold. Rebuild all three with `python scripts/build_ai_dashboard_fixture.py`
from the repository root. The live context reads allow-listed PostgreSQL views under the
`feedback_dashboard` role and deduplicated ClickHouse projection facts. Restricted
feedback text, raw metadata, worker errors, and outbox payloads are outside this boundary.

## Prerequisites

- [.NET SDK 10.0.401](https://dotnet.microsoft.com/en-us/download/dotnet/10.0), selected by the repository `global.json`
- Docker, only when building or running the container

Run all commands from the repository root.

## Restore, format, build, and test

```bash
dotnet restore services/api/FeedbackIntelligence.sln --locked-mode
dotnet format services/api/FeedbackIntelligence.sln --no-restore --verify-no-changes
dotnet build services/api/FeedbackIntelligence.sln --configuration Release --no-restore
dotnet test services/api/FeedbackIntelligence.sln --configuration Release --no-build --no-restore
```

NuGet dependencies use exact versions and both projects commit `packages.lock.json`. CI automatically enables locked restore through `Directory.Build.props` when `CI=true`.

## Run locally

```bash
dotnet run --project services/api/src/FeedbackIntelligence.Api
```

In another terminal:

```bash
curl --fail http://localhost:5080/health
```

The endpoint returns `Healthy` as plain text when the API process is healthy.

## Dashboard routes

```text
GET /api/v1/dashboard/metadata?context=demo|live
GET /api/v1/dashboard/trends?context=demo|live&sourceKey=...
GET /api/v1/dashboard/evaluation?context=demo|live
GET /api/v1/dashboard/overview?context=...&sourceKey=...&from=...&toExclusive=...
GET /api/v1/dashboard/signals/{signalId}?context=...&sourceKey=...&from=...&toExclusive=...
GET /api/v1/dashboard/signals/{signalId}/evidence?context=...&sourceKey=...&from=...&toExclusive=...&page=1&pageSize=10
GET /api/v1/dashboard/evidence/{feedbackId}?context=...&decisionId=...
POST /api/v1/feedback
```

Times are UTC and ranges are `[from,toExclusive)`. Evidence ordering is occurrence time descending and feedback ID ascending; `pageSize` is capped at 50. Invalid requests, unknown sources, and unavailable live stores use HTTP Problem Details.

The trends route exposes typed `simple_rate_change` and `candidate_statistical`
configurations. Both use exact adjacent 7/28-day UTC windows. Their committed demo
fixtures are generated from frozen 10,000-record planted-incident reports; counts,
rates, posterior probability for the Beta-Binomial candidate, alert episodes, and
incident matches are measured detector-only results. Set
`Trend__Algorithm=candidate_statistical` to inspect the candidate; the measured
promotion gate keeps `simple_rate_change` as the default because the candidate's
mean delay is higher. Live trends remain explicitly `unavailable` with reason
`awaiting_calibration` and expose no trend values or raw evidence until calibration.

The evaluation route exposes the measured 480-record local SemIf comparison
against an interim Sol-medium AI reference, including primary-topic macro-F1,
accuracy, completion/error counts, and English/Swedish slices. The response labels
the reference as `ai_reviewed_not_human_gold`. It also exposes the closed 192-record
GPT-5.4 Mini partial experiment, its partial topic metrics, owner-reported spend,
the linearly extrapolated 480-record cost, and SemIf's measured local token count
with zero provider API charge. Live evaluation remains unavailable
with reason `awaiting_human_labels` and never exposes the interim demo result.
SemIf ingestion jobs require a native Apple Silicon worker installed with the
worker's `semif` extra; the current Linux Compose worker supports fixture replay,
rules, and the opt-in hosted LLM path.

Configure live reads with these server-side settings (environment variables use double underscores):

```text
ConnectionStrings__Dashboard
Dashboard__ClickHouse__Url
Dashboard__ClickHouse__User
Dashboard__ClickHouse__Password
```

Ingestion is disabled by default. Enable it only for a private/local runtime with
`Ingestion__Enabled=true`, set a non-empty `Ingestion__ApiKey`, and configure
`ConnectionStrings__Operational`. Clients pass the key in
`X-Feedback-Ingestion-Key`. The key comparison is constant-time and the dedicated
fixed-window policy defaults to 30 requests per source IP per 60 seconds; configure
it with `Ingestion__RateLimitPermitLimit` and `Ingestion__RateLimitWindowSeconds`. The
endpoint accepts the camel-case `feedback-record/1.0.0` shape documented in
`contracts/api/feedback-ingestion-v1.schema.json`. It checks the deterministic
feedback UUID, a 10,000-character text limit, UTC timestamps, rating/product
invariants, and payment-card candidates before writing. New jobs return `202`;
idempotent replays return `200` with the existing job and current status. The
database transaction runs under the `feedback_api` role.

Set `Observability__Enabled=true` and `OTEL_EXPORTER_OTLP_ENDPOINT` to export API
request, `feedback.ingest`, and `feedback.persist` traces plus ingestion outcome,
error, and latency metrics. Health requests are excluded. The API writes the active
W3C trace context to the processing job so the worker can continue the trace. No
feedback body, API key, or exception message is attached to custom telemetry.

Apply all ordered files in `infra/postgres/migrations/` to existing databases before
enabling live reads and ingestion. Migration 003 adds persisted trace context. The
API executes `SET ROLE feedback_dashboard` on every opened PostgreSQL read
connection. When current policy output is uncalibrated, processing counts remain
available while analytical percentages stay null with an explicit `uncalibrated`
reason.

ASP.NET Core loads `appsettings.json`, optional environment-specific `appsettings.{Environment}.json`, environment variables, and command-line values through the default `WebApplication` configuration pipeline. Use double underscores for nested environment keys, such as `Logging__LogLevel__Default=Debug`.

## Run in Docker

The Docker build context is the repository root so the image can include the root license files. The multi-stage image runs as the unprivileged user supplied by the official .NET image and listens on port 8080.

```bash
docker build --file services/api/Dockerfile --tag feedback-intelligence-api .
docker run --rm --publish 127.0.0.1:8080:8080 feedback-intelligence-api
curl --fail http://localhost:8080/health
```
