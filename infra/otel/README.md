# OpenTelemetry runtime

The optional Compose `observability` profile starts the Collector Contrib 0.160.0
with OTLP gRPC/HTTP receivers, an explicit attribute allow-list, batching, and the
local debug exporter. Set `OTEL_ENABLED=true` to enable the ASP.NET Core API and
continuous Python worker exporters. The API persists its W3C parent context with
each processing job, so the worker's `feedback.process` span continues the same
trace across the asynchronous PostgreSQL boundary. Decision persistence writes a
new parent context to the outbox row, allowing `analytics.project` to continue that
same trace across the second lease boundary.

The allow-list is enforced in application helpers and again by the Collector
redaction processor. Feedback bodies (including redacted text), credentials,
customer identifiers, exception messages, and provider payloads are excluded.
Stable record/job/decision IDs may appear in traces; metric dimensions are limited
to low-cardinality engine, schema, source, outcome, destination, and error-type
fields. Canary tests cover both boundaries. See
[privacy boundaries](../../docs/privacy.md).

The debug exporter is for local inspection. A hosted deployment still needs an
authenticated and encrypted telemetry backend, retention policy, and access
controls.

Validate the configuration with the same image used by Compose:

```sh
docker compose run --rm --no-deps otel-collector validate --config=/etc/otelcol/config.yaml
```
