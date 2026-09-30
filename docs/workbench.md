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
6. Inspect coverage, distributions, daily counts, exploratory changes, record
   evidence and matched-run disagreements. Export CSV/JSON with provenance.

The separate recorded showcase preserves its 480-record SemIf/rules/Sol views
and closed 192-record paid experiment. The larger 10,000-record rules scenario
uses the deterministic generator; it does not create additional frozen model
predictions or improve the measured benchmark.

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
selected account's current catalog.

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
and interrupted/usage-limited streams. The ChatGPT integration must remain marked
**live verification pending** until the owner completes a real sign-in and
explicitly approves a small classification run. The implementation and mocked
tests alone do not establish real account admission.
