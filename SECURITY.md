# Security

This repository supports a recorded synthetic showcase, an interactive single-owner
local Workbench and an opt-in legacy ingestion pipeline. It is not approved for
public hosting or real customer-service operation. Published ports bind to loopback.
The Workbench requires an owner session; legacy dashboard reads do not have user
authentication. Do not expose either local installation on an untrusted network.

## Reporting a vulnerability

Do not publish secrets, customer information, or exploit details in a public issue.
When this repository is hosted on GitHub, use **Security → Report a vulnerability**
if private vulnerability reporting is enabled. If no private channel is available,
open an issue requesting a private contact route without disclosing the vulnerability.
No response SLA or private contact address is established yet.

## Implemented boundaries and limits

- Workbench provider credentials use an encrypted server-side vault and protected
  persistent installation keys. Startup generates file-backed owner/service/database
  secrets with restricted permissions; none are returned to browser storage or run
  payloads. The API reads both ciphertext and keys, so this is at-rest protection,
  not isolation from an API or OS-owner compromise. Legacy CLI credentials use
  ignored environment configuration. No direct browser model calls are implemented.
- Local Workbench commands require a live HttpOnly/SameSite session. Mutations also
  require exact origin and CSRF; internal command and run-bound credential broker
  interfaces independently require a service bearer. OAuth retains state, PKCE,
  nonce, verified identity, serialized refresh and explicit plan permission checks.
- Owner-selected uploads have admitted parser subprocesses, streamed line/XLSX
  handling, scalar JSON structure validation, 30-second timeout and 64 MiB graph/
  transfer limits. Linux Docker enforces a 512 MiB child memory ceiling. Native macOS
  has narrower guarantees. The child receives no credential environment variables;
  this is resource isolation, not a separate OS/container security principal.
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

Workbench Compose uses separate API, worker and maintenance PostgreSQL LOGINs with
capability grants. The combined trusted worker mounts all three DSNs; SQL-role
separation is not process isolation. Dataset deletion hides/cancels work and confirms
purge across PostgreSQL and ClickHouse. Original-text export confirmation is an owner
UI safeguard, not another backend authorization principal.

Legacy Compose uses shared development LOGIN credentials with capability roles.
Before hosted real-data use, establish tenant/evidence authorization, independently
isolated service credentials, secret rotation, TLS, backup/retention policy and an
operational incident process. Local tests do not establish those hosted boundaries.

The v0.2.0 review repairs upload resource amplification and updates advisory-matched
dependencies. Optional SemIf uses explicit fixed dependency overrides; historical
benchmark configuration remains unchanged. See the
[release verification](docs/quality/v0.2.0-release-review.md) for exact evidence.

See [privacy design](docs/privacy.md) and the [audit verification record](docs/quality/verification-report.md).
Tests cover specific canaries and permission paths; they are not a security certification
or legal-compliance claim. Browser and hosted-environment verification are separate gates.
