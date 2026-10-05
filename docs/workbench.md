# Interactive local workbench

The workbench adds user-uploaded datasets and executable classification runs to
the recorded portfolio showcase. Start it on macOS or Linux with Docker Desktop
running:

```sh
python3 scripts/start_workbench.py
```

Open [localhost:8081/#workbench](http://localhost:8081/#workbench). Unlock it with
the private code in `.workbench-runtime/api/owner-code`. The script provisions
separate PostgreSQL login principals and protected installation files. It does
not print credentials. The runtime uses its own database volumes and does not
alter existing demo storage. Uploaded data, keys and the vault are excluded from
Git and Docker build contexts. Local persistence is not a backup; retain your
source files and explicitly exported results separately.

Operators can lower the upload ceilings with `WORKBENCH_MAX_UPLOAD_BYTES`,
`WORKBENCH_MAX_RECORDS`, and `WORKBENCH_MAX_TEXT_CHARS` before starting the runtime.
Defaults and hard ceilings are 25 MiB, 10,000 records, and 20,000 text characters.

## The workflow

1. Upload CSV/TSV, XLSX, a JSON array, JSONL, or paste one comment per line.
2. Select a worksheet and map feedback text plus any source ID, date, rating,
   language, channel, product or group fields. Dates without an offset require a
   timezone. Missing dates remain missing.
3. Review accepted/rejected rows, duplicate IDs, repeated text, missing dates and
   prepared text. Explicitly approve importing valid rows.
4. Choose the general or retail topic template, or save an edited revision.
   Lower keyword priority numbers win; competing matches remain inspectable.
5. Run free keyword classification, or connect ChatGPT/API billing and explicitly
   approve an up-to-25-record representative sample before a full run.
6. Inspect coverage, distributions, dated volume, exploratory changes, record
   evidence and matched-run disagreements. Export CSV/JSON with provenance.

The separate recorded showcase preserves its 480-record SemIf/rules/Sol views
and closed 192-record paid experiment. The larger 10,000-record rules scenario
uses the deterministic generator; it does not create additional frozen model
predictions or improve the measured benchmark.

## Inspect and drill into results

Results menus show observed topics, sentiment, language, product and group with
counts across every successful record in the selected run. They default to **All**.
Topics and sentiment come from saved decisions; other dimensions come from imported
metadata. **Not supplied** and **Unavailable** are explicit missing selections,
distinct from a literal product named `None`. Active filter chips and Clear all
filters show the current cohort. Date bounds include both displayed UTC days;
undated records are excluded only when a date bound is selected.

Hover or keyboard focus previews a value. Click or Enter pins its counts, scope,
coverage and provenance. Desktop inspection uses a nonmodal side panel; phones use
a scrollable modal sheet. Escape dismisses details and restores focus. Period and
category inspectors offer **View matching records**, which applies a filter and
returns to the first evidence page. Record details show prepared text, supplied
metadata and ratings, actionable outcomes, competing keyword matches, available
sentiment matches, redactions and model identities.

The responsive volume chart uses UTC calendar periods, from days through weeks,
months, years and multi-year groups, with no more than 60 displayed periods.
Underlying daily counts and nested topic counts remain available in the data
disclosure. Unobserved dates have unknown coverage, never invented zero counts.
Use Left/Right, Home/End and Enter to inspect chart periods by keyboard.

Switching runs clears filters, evidence, inspections and analyses. Moving between
views preserves the current workflow. Results keep their filter controls during
refresh and provide retry actions after failures. Superseded results, trends,
comparisons and exports cannot replace the newly selected scope.

Trend detection cannot run with a topic filter: that would make every selected
record belong to the topic and create a misleading 100% rate. Clear the topic
filter first. Other filters define the cohort; sparse/unknown coverage remains
unavailable. Comparisons are **whole-run shared-record agreement**, independent of
Explore filters, and require compatible dataset, template and protocol snapshots.

### Results interface and provenance

`GET /api/v1/workbench/runs/{id}/results` retains categorical query parameters and
adds `missing=sentiment,language,product,group`, `dateFrom=YYYY-MM-DD` and
`dateTo=YYYY-MM-DD`. Conflicting value/missing selections and malformed or reversed
dates produce validation errors. The same normalized selection applies to trends
and exports. Results return:

- `facets` for all five dimensions, each choice with `{value, label, count}`;
  missing values use `null`.
- `summary.dailySeries` with `{date, total, topics}`; topic IDs such as `date` and
  `total` cannot overwrite daily metadata. Legacy `days` and `groups` remain.
- `filters`, `readAt`, `page`, `pageSize: 50`, `filtered` and `returned`. Requested
  pages are clamped to the available range, including an empty first page.

Run counters, facets, summary and evidence use one repeatable-read PostgreSQL
snapshot. Export includes every matching record across pages and records the
normalized filters. Prepared text is the default; original text requires a local
confirmation. JSON adds `analysisImplementation`; CSV appends `filters` and
`analysis_implementation` columns. The corrected detector identity is
`workbench-detectors/1.0.1`. Statistical thresholds, protocol hash and immutable
classification snapshots remain unchanged; analysis identity includes the method,
filters and cohort inputs.

## Boundaries and persistence

React owns mapping and run controls. The .NET API owns local sessions, origin/CSRF
checks, credentials, OAuth and the public request boundary. The authenticated
internal Python service normalizes imports and persists workbench commands into
PostgreSQL, then processes jobs using a durable scoped lease loop. New workbench
tables reuse the operational lease/outbox pattern without changing the existing
fourteen-question ingestion contracts. Each run stores its immutable dataset,
template, rules/model, privacy and statistical protocol snapshots.

Classification results and template revisions cannot be edited. Ordinary API and
worker principals cannot delete results. A separate purge principal removes
dataset content after cancellation and confirmed ClickHouse deletion. Deleted
datasets are immediately hidden from evidence reads; the deleting state remains
until purge succeeds. Active leases fence late writes and delay purge until
in-flight work can no longer write. Projection retries share stable IDs and use
the dedicated `workbench_effective` deduplicated view, never legacy rollups.

The UI reports committed PostgreSQL classification results and their projection
backlog; ClickHouse stores the text-free analytical projection. Zero observations
on a date are unknown coverage, not an invented zero. Statistical detection is
exploratory and requires complete observed date coverage for its windows.

## OpenAI usage

Use **Continue with ChatGPT** to register this installation through the official
open-source OAuth flow. A verified identity alone does not authorize plan usage.
Account registrations, issued client IDs, scopes and credentials remain separate.
The server verifies state, nonce, signature, issuer, audience and expiry, uses a
stable host ID, and serializes refresh-token renewal. The model picker reads the
selected account's current catalog. Connections and Classification share that catalog;
listed GPT-6/GPT-6.1 models and future releases appear without a version whitelist.
The picker refreshes on connection/view changes, every five minutes while visible,
and after a stale window-focus return. **Refresh models** retries immediately.
A failed refresh marks the previous list stale and blocks new AI processing.
Selections are preserved while available; removed models require another choice.

Choose **Reasoning effort** alongside the model. **Provider default** omits the
API effort parameter; supported explicit values depend on the model. GPT-6.1 Sol
and GPT-6 Astra support Low/Medium/High/Extra high/Max; GPT-6 Sol/Luna also support
None. GPT-5.4 Mini/nano use their documented profile. Provider metadata takes
precedence over dated local profiles; unknown capabilities allow provider-default
processing without invented effort choices. See the official
[reasoning guide](https://developers.openai.com/api/docs/guides/reasoning).
Higher effort can consume more usage and time; improved classification is not
promised. API pricing remains a separately dated reference or unavailable.

The server validates the model and effort before creating a run. Explicit effort
is saved in the run snapshot and recorded output, consent preview and exports;
samples and full runs must match it. Resume uses saved settings. Existing records
without an effort field remain unchanged and are labeled not explicitly recorded.
Comparisons show each configuration; different-effort agreement remains exploratory.
The models endpoint adds optional `reasoningEfforts`, `capabilitySource` and
`capabilityReviewedAt` fields. Run creation adds nullable `reasoningEffort`; null
means Provider default. These additions require no database migration.

API-key mode is separate API billing and must be explicitly selected. The tool
never changes billing mode automatically. Dated standard-rate references for
[GPT-5.4 Mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini) and
[GPT-5.4 nano](https://developers.openai.com/api/docs/models/gpt-5.4-nano) were
reviewed on 2026-09-30. Other models show unavailable pricing. Sample-based full-run
extrapolations are estimates, not invoices. Reused sample records do not count
again as new-run token usage. The interface does not invent allowance percentages or
convert recorded tokens into remaining plan usage. Manage plan limits in ChatGPT
settings. Model capability and account-policy errors pause or fail the affected
run, with successful records retained.

Responses use `store:false` and `stream:true`; only a completed, schema-valid
response becomes a successful classification. Imported feedback is treated as
untrusted data and receives no executable tools. The shared local redactor runs
before rules and model calls. Redaction is a bounded detection layer, not a
guarantee that arbitrary personal information has been removed. Review prepared
text before approving external processing.

Secrets are protected by the local server vault and installation key, not stored
in browser storage or job payloads. Restrict access to the local OS account and
runtime directory. Hosted multi-user operation is out of scope.

## Verification

```sh
python3 scripts/quality_workbench_check.py
python3 scripts/seed_workbench_demo.py
```

This exercises the real local API, PostgreSQL worker, projection and purge using
synthetic test records. Ordinary CI makes no paid inference calls. Unit tests
cover import formats, validation, redaction, rules, sampling, unknown time
coverage, OAuth claims/signatures, encrypted credentials, replay, plan scopes,
and interrupted/usage-limited streams. Existing owner-created ChatGPT samples provide bounded live evidence: 25/25
successes with gpt-5.6-luna at Low effort and 25/25 with gpt-5.6-sol at Provider
default. Requested and returned model identities matched. This does not verify
every available model, account, effort or subscription; ordinary CI uses mocks.
No additional sign-in or inference was initiated for the v0.2.0 release. See the
[release review](quality/v0.2.0-release-review.md).

See the [v0.1.5 Results review](quality/results-inspection-review.md) for browser,
recovery, filtering and compatibility evidence and its limitations.

## Expired or revoked ChatGPT sessions

If OpenAI rejects renewal with a terminal code such as `invalid_grant`, the model
picker stays disabled and offers **Reconnect ChatGPT account**. Open Connections
and reconnect the existing account; the saved registration/client ID is reused.
Only unusable access/refresh tokens are cleared. Account identity, registration,
datasets and completed results remain. Temporary provider failures preserve
credentials and allow retry; no fallback to API billing occurs.

The app displays only allow-listed error codes and app-owned recovery text. Provider
response bodies and credentials remain outside UI diagnostics. Reconnecting does
not start classification or establish that real inference has been verified.

## v0.2.0 import resource boundary

The existing 25 MiB, 10,000-record and 20,000-text-character ceilings remain.
JSON/JSONL/NDJSON support scalar-valued objects (strings, numbers, booleans, null);
nested cells, duplicate keys and nonfinite numbers are rejected. Line formats and
XLSX rows are streamed, preserving missing dates and original source hashes.

Before decoding, one parser slot and a preview cache slot must be available. The
parser is a fresh credential-free subprocess with a 30-second wall timeout,
including output transfer. Linux Docker enforces a 512 MiB child address-space
ceiling. Native macOS has timeout/structural limits but no claimed equivalent
address-space enforcement; Docker is the supported bounded installation.

Each retained Python preview graph and serialized child transfer is capped at
64 MiB. Four previews expire after ten minutes; previews borrowed by validation
or commit remain counted until the operation releases them. Workbook metadata
entries are capped at 1 MiB; streamed XML is limited to two million elements and
32 levels. Macros, external links, encrypted entries, formulas and XML entities
remain unsupported. Combined resource ceilings can reject files below individual
byte/row limits: split the file or remove columns. No truncation is performed.

Busy admission returns a retryable HTTP 429. Other invalid/resource-limited imports
return a safe validation error. The internal command envelope also has bounded
structure and four admitted handlers; health remains separately available.
