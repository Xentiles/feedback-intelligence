# Security

This repository supports a local synthetic demonstration and an opt-in ingestion
pipeline. It is not approved for public hosting or real customer data. Container
ports bind to loopback and optional storage requires locally supplied passwords.
The write endpoint has an API key and rate limiter; dashboard reads do not have
user authentication. Do not expose live dashboard metadata on an untrusted network.

## Reporting a vulnerability

Do not publish secrets, customer information, or exploit details in a public issue.
When this repository is hosted on GitHub, use **Security → Report a vulnerability**
if private vulnerability reporting is enabled. If no private channel is available,
open an issue requesting a private contact route without disclosing the vulnerability.
No response SLA or private contact address is established yet.

## Implemented boundaries and limits

- Provider credentials are server-side environment settings, excluded from Git and
  container build contexts. No browser model calls are implemented.
- A deterministic local privacy boundary constructs an allow-listed model state;
  payment-data canaries are rejected. Regex redaction is a baseline, not a guarantee
  of complete PII removal. See the documented language/pattern limits.
- Worker operational telemetry uses IDs, stages and error classes. Persisted failure
  messages omit exception text. Do not add raw provider responses to diagnostics.
- Restricted feedback text lives in PostgreSQL. The projector capability role has
  no SELECT permission on that table. Live dashboard bodies/excerpts are withheld;
  this does not make its remaining identifiers and classifications public data.
- Decisions, answers, review labels and audit events have immutable database
  triggers. Outbox projection is at-least-once with deduplicated analytical reads,
  not a cross-database exactly-once transaction.
- Uncalibrated answers remain analytically ineligible. Fixture/example policy flags
  are never evidence of calibrated human-gold performance.

Compose uses shared development LOGIN credentials with capability roles. This is
not hosted credential isolation. Before real-data hosting, implement separate
service principals, authenticated evidence authorization, retention/deletion rules,
secret rotation, TLS/deployment policy and an operational incident process.

See [privacy design](docs/privacy.md) and the [audit verification record](docs/quality/verification-report.md).
Tests cover specific canaries and permission paths; they are not a security certification
or legal-compliance claim. Browser and hosted-environment verification are separate gates.
