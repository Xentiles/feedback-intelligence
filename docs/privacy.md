# Privacy and traceability boundaries

**Status: deterministic local redaction, restricted persistence, and telemetry
allow-lists implemented; advanced detection and retention controls remain deferred.**

The public project is synthetic-first. No real feedback, customer identifiers, or
provider secrets belong in the repository. Dataset adapters can normalize local
source text, but raw and normalized external files are Git-ignored.

Every `DatasetProvider` output has `privacy_status: uninspected`. This marker is a
hard boundary: normalization, joining, validation, and profiling do not make a
record safe for an external model. The dataset CLI does not call AI services.

The Python worker's `PrivacyBoundary` creates a separate
`ModelSafeFeedbackState`; it never mutates a canonical `FeedbackRecord`. Its
decision state contains only:

- locally redacted feedback text;
- a bounded language tag, when supported (language, optional script and region;
  no private-use extensions);
- a canonical channel: `product_review`, `delivery_survey`, `support_ticket`,
  `return_feedback`, or `site_feedback`.

Unsupported language/channel metadata is omitted from model state, while the
canonical local record remains unchanged. The model-state type also rejects
unsupported metadata when constructed directly. Evaluation prediction runs reuse
this same boundary: supported identifiers are redacted and payment credentials
produce a text-free error row before any engine call.

It excludes the title, source record ID, order ID, rating, product and seller IDs,
operational context, adapter metadata, and internal feedback ID. This allow-list
prevents newly added canonical fields from silently crossing the provider boundary.
The internal result retains only a stable feedback ID, source provider, a SHA-256
hash of redacted text, and redaction counts for audit purposes.

## Deterministic baseline

The first boundary performs local replacements for:

| Category | Treatment |
| --- | --- |
| E-mail | `[EMAIL]` |
| Phone-like value | `[PHONE]` |
| Valid Swedish personnummer pattern | `[NATIONAL_ID]` |
| Labelled customer/account identifier | `[CUSTOMER_ID]` |
| Labelled order identifier | `[ORDER_ID]` |
| Name after explicit English/Swedish name labels | `[NAME]` |
| Recognised English/Swedish street or postal address | `[ADDRESS]` |
| Valid payment-card number, IBAN, or labelled CVV/CVC | Reject the record from the decision path |

Matched values and positions are never retained in the redaction summary. The
worker's trace and metric helpers accept only explicit scalar attribute allow-lists;
the Collector redaction processor enforces a second allow-list. Neither layer
accepts raw/redacted bodies, credentials, customer IDs, exception messages, or
provider payloads. High-cardinality workflow IDs are allowed only in traces.
Worker spans disable automatic exception events and exception-derived status
descriptions, including nested spans. Failures retain only the error class and a
generic error status. ClickHouse error bodies are not copied into exceptions.

Run the boundary without any external call:

```sh
cd services/decision-worker
uv run --locked feedback-privacy synthetic
uv run --locked feedback-privacy olist --json
```

The command reports how many canonical records can proceed and how many were
rejected for payment data. It never prints feedback bodies.

The baseline is deliberately conservative and is not a general named-entity
recognition system. Unlabelled names, unusual addresses, identifiers in unsupported
formats, and context-dependent personal information can remain. Phone detection
can also over-redact number-like text. Production or user-supplied data therefore
needs source-specific minimisation, broader evaluated detectors, manual review
where appropriate, and retention/access controls. These are privacy engineering
measures, not a claim of legal compliance.

Every external adapter accepts only `ModelSafeFeedbackState`, never
`FeedbackRecord` or arbitrary dictionaries. The local SemIf adapter serializes the
same allow-listed state exercised by the privacy canaries.
Synthetic scenario IDs, incident IDs, and ground truth remain excluded to avoid
evaluation leakage. Canary tests capture both the model-state serialization and
telemetry event and fail if planted e-mail, phone, national ID, customer/order ID,
or source-only fields appear.

Raw text belongs in restricted PostgreSQL storage. ClickHouse should receive only
derived signals and stable pseudonymous identifiers. Logs, traces, and metrics
must not contain feedback bodies, including redacted text, or full model state.
High-cardinality source/decision IDs belong in traces rather than metric dimensions.

Decision envelopes retain source identity, input hash, schema identity,
requested/resolved model, and execution metadata without feedback bodies. The
policy field remains null until calibrated routing exists. Keep historical model
output immutable; human review labels must not silently overwrite it. Aggregates
must preserve a route back to the contributing accepted dimensions and records.

The local/private ingestion endpoint requires a configured API key and applies a
fixed-window source-IP rate limit. Restricted database roles and production
telemetry filtering exist, but managed identity, separate deployment credentials,
TLS termination, retention automation, authenticated telemetry storage, and broader
evaluated privacy fixtures remain necessary before real-data or hosted operation.
These practices alone do not establish legal compliance.
