# Storage and projection

The storage pipeline implements the plan's PostgreSQL operational boundary and
ClickHouse analytical boundary without introducing a broker.

From the repository root, set local database passwords in the ignored `.env`, then
run the deterministic nine-record fixture pipeline:

```sh
docker compose --profile pipeline up --build \
  --abort-on-container-exit --exit-code-from pipeline-worker pipeline-worker
```

The first run inserts nine feedback records, nine jobs, nine immutable decisions,
126 typed answers, and nine outbox events. The policy remains uncalibrated, so all
nine projection events are marked `skipped.uncalibrated`; ClickHouse contains zero
signal facts and zero aggregate rows. Running the same command again reports zero
new jobs, processing, or projection work.

For the application path, enable the otherwise read-only API and start the continuous
consumer with:

```sh
INGESTION_ENABLED=true INGESTION_API_KEY='replace-locally' \
  docker compose --profile runtime up -d --build \
  postgres clickhouse api processing-worker
```

`POST /api/v1/feedback` validates a canonical camel-case record, derives the same
UUIDv5 job identity as the Python repository, and returns `202` when it creates a
job. Repeating the same request returns `200` and the existing job. The worker polls
with a bounded interval, claims expired or pending leases, and continues after
recording retryable failures. Uncalibrated output closes the outbox as
`skipped.uncalibrated` rather than becoming an analytical fact.

## Transaction and retry boundaries

Canonical feedback and its processing job are inserted in one PostgreSQL
transaction. A worker claims a job with an expiring lease, performs local redaction
and the selected decision engine call, then commits the immutable run, all answers,
the projection outbox event, and successful job state together. Failure records a
bounded error and exponential retry time; exhausted work becomes `dead`.

Forward migration `004_lease_exhaustion.sql` also terminates an expired final
attempt when its worker crashed before the failure callback. It respects each
row's retry limit and does not take an unexpired owner's lease. Failure messages
retain the stage and exception class, not exception text that could contain PII.

Migration `005_semantic_ingestion_identity.sql` handles serializer differences
between API and Python imports. On a checksum mismatch, a SECURITY INVOKER function
compares the complete persisted content (including restricted text) using JSONB
numeric/property-order equality and normalized UTC instants. Historical writer
hashes are preserved, not treated as a universal cross-language canonical digest.
Changed source content/version remains a conflict; it is never silently overwritten.
Only the API/worker roles can call the comparison; the projector gains no text access.
Apply forward migrations with the documented `feedback-storage migrate` path before
running updated writers against an existing database. This audit used isolated
databases and did not migrate an existing developer volume. With locally configured
database passwords, the forward-only command is:

```sh
docker compose --profile pipeline run --rm --build \
  --entrypoint feedback-storage pipeline-worker migrate --json
```

The projector claims outbox rows through the same lease pattern. A calibrated,
eligible event is inserted with a deterministic ClickHouse deduplication token and
then recorded in the PostgreSQL projection ledger. A crash between those steps can
repeat the ClickHouse request, so table-level insert deduplication complements the
stable event identity. Dashboard queries must still use the model designed for
accepted facts rather than relying on eventual `ReplacingMergeTree` merges.

Migration `003_processing_trace_context.sql` adds optional W3C `traceparent` and
`tracestate` fields to processing jobs and outbox events. The API stores the current
ingestion span context with the job; the worker resumes it at `feedback.process`
and stores its decision-persistence context with the outbox event. The projector
then resumes that context at `analytics.project`, preserving one distributed trace
across both asynchronous PostgreSQL boundaries.

Migration `002_trend_inputs.sql` adds immutable decision time, canonical source
identity, and explicit nullable accepted-positive classifications to the fact
boundary. Its `daily_detector_inputs` view deduplicates projection retries and
selects the latest decision per feedback item inside an exact
source/schema/model/policy cohort before producing integer daily numerators and
denominators. It does not infer classifications from probability thresholds or use
the older insert-driven `SummingMergeTree` rollups as a trend source of truth.

## Privacy and immutability

Raw text is isolated in `restricted_feedback_text`. The API/worker capability roles
can access it; projector and analytics roles cannot. Projection events and
ClickHouse tables reject extra fields and contain no feedback body. Database
triggers reject updates or deletes to decision runs, answers, reviewer labels, and
audit events. Corrections create new records rather than rewriting provenance.

## Current boundary

The fixture pipeline remains the deterministic public demo path. The write API is
disabled by default; when enabled it requires a configured ingestion key and has a
dedicated fixed-window limiter. Cross-service traces and low-cardinality metrics
are opt-in and privacy-filtered. Managed identity, separate LOGIN credentials,
retention jobs, and calibrated eligible facts remain later work. The live
detector-input view therefore remains empty. PostgreSQL and ClickHouse provide the
persistent contracts those paths will use.
