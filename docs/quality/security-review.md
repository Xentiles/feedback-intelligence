# Pre-publication security review — 2026-09-20

Codex Security Standard scan `8d02ac12-cec2-4615-ac99-c4e3e8ee2e01` reviewed the
pre-commit publication snapshot. It reported three medium-severity privacy
findings and no high or critical findings. The sealed scan describes the source
**before** the repairs below; it is not a clean post-fix scan.

The source audit covered 329 of 344 candidate files, including all first-party
application code, tooling, tests, schemas and infrastructure. Large synthetic
fixtures and dependency lockfiles received structural inspection. Fifteen raster
assets and historical generated reports received narrower inspection, so the scan
records partial coverage. No live provider calls or runtime exploits were used
during the static audit. Upstream dependency code, current vulnerability feeds,
binary decoder safety and legal compliance were not certified.

## Repairs and regression evidence

| Finding | Repair | Local regression evidence |
| --- | --- | --- |
| Free-text language/channel could cross the model boundary | Only bounded language tags and canonical channel categories enter model state; unsupported metadata stays local. Direct model-state construction rejects unsupported values. | Email, card and CVV canaries in both metadata fields never enter outbound state. |
| Evaluation prediction bypassed redaction | Evaluation uses the same privacy preparation as runtime processing; payment rejection becomes a text-free error row before inference. | Capturing fake engine receives redacted text and counts; card, CVV and IBAN inputs never call it. |
| Automatic exception recording bypassed telemetry filtering | Disable exception events and exception-derived status descriptions on every worker span. Keep generic error status/class; discard ClickHouse response bodies. | In-memory exporter captures nested failures without message, stack or status-description content; HTTP-error regression verifies payload omission. |

The repairs passed 116 worker tests, Ruff and strict mypy. The web suite passed
25 tests plus formatting, lint, type checks and production build. Containerized
API formatting/build passed with zero warnings; 42 ordinary API tests passed and
the separately enabled PostgreSQL interoperability test passed in the isolated
ingestion suite. Disposable storage and projection checks passed, including lease
fencing, immutability, restricted-text grants and duplicate projection behavior.
Six demo HTTP smoke groups and 100 warm samples per measured route also passed.

## Release corrections

Contracts CI now regenerates its ignored deterministic source before checking
dashboard fixture parity. Container smoke compares the complete evaluation
response with the public contract example. The local demo harness and component
README commands use the root Docker build context. Screenshot extensions match
their JPEG contents.

These changes make the existing local-demo controls more consistent. They do not
establish hosted-service readiness: authentication for dashboard access, separate
database principals, TLS, retention and broader evaluated privacy detection remain
required for real data. Human annotation and calibration remain incomplete. The
closed paid experiment was not resumed.

Remote CI evidence is recorded separately in [release readiness](../release-readiness.md).
