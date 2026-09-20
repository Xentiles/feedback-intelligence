# Project audit — 2026-09-20

Feedback Intelligence is an independent portfolio project, not commissioned,
sponsored, endorsed or used by Inet. This audit evaluates its current local
synthetic demonstration and repository presentation. It does not promote the
project to a real-customer service or invent calibration to populate live analytics.

## Executive assessment

The overview → signal → contributing feedback → decision journey is implemented.
The system has meaningful boundaries: canonical providers, a local model-state
privacy boundary, immutable PostgreSQL decisions, leased jobs/outbox, body-free
analytical events, and separate illustrative/live reads. The main work in this
pass was repairing consistency and failure paths and making those claims testable.

Twenty substantive findings: **14 resolved, 6 open or gated**. No P0 was found in
this bounded audit; that is not a claim of exhaustive security assurance. Counts:

| Severity | Resolved | Open / gated | Total |
|---|---:|---:|---:|
| P0 | 0 | 0 | 0 |
| P1 | 6 | 1 | 7 |
| P2 | 8 | 4 | 12 |
| P3 | 0 | 1 | 1 |

AUD-004 was a rejected hypothesis, not a finding: a numbered source listing was
misread as an extra constructor argument; the untouched API build passed.

The earlier aggregate completion percentages in conversation are not release
evidence. Use the named gates in [verification](verification-report.md), the
[architecture review](architecture-review.md), [requirements matrix](requirements-traceability.md)
and [executable QA requirements](qa-plan.md).

## Findings register

The source paths below are repository-relative; symbols are stable references.
“Resolved” means implemented and covered by the stated checks, not deployed into
an existing developer volume. Models are actual delegated selections; “lead” is
the integration owner whose runtime model was not independently selectable.

| ID / category / severity | Requirement; expected → observed baseline; root cause and impact | Repair / acceptance evidence | Dependency, risk, owner and final state |
|---|---|---|---|
| AUD-001 Reliability P1 | QA-STO-01: crashed final attempt must terminate. `001_operational_model.sql` claim predicates exclude `attempt_count >= max_attempts`; final crashed leases stayed running/publishing forever. Callbacks also hardcoded 5/8 instead of row limits. | Forward migration004 reaps expired exhausted work without taking active leases; callbacks use row limits. `quality_storage_check.py` reproduces pre004 failure then verifies limits, concurrent ownership and stale rollback. | Requires migration004 on existing volumes; protected SQL reviewed by lead. Astra high. **Resolved**. |
| AUD-002 Ingestion P1 | QA-ING-02: equivalent inputs across providers should deduplicate. API `CanonicalSha256` and Python `enqueue_record` serialize differently; identical data appeared changed. | Migration005 supplies invoker-only semantic stored-content comparison on hash mismatch. No row/hash rewrite. Python/API real DB test covers both directions, reordered Unicode metadata, equivalent numeric spelling and UTC suffix, genuine conflicts, exactly two jobs and projector denial. | Requires migration005 before updated writers; restricted reads remain API/worker only. Lead implementation, Astra review. **Resolved**. |
| AUD-003 Contract P2 | QA-ING-03: nullable operational timestamps allowed. `timestamp?.Offset != TimeSpan.Zero` rejected null values, blocking valid undelivered-order feedback. | `IngestionValidator` checks only present values; endpoint regressions null/omitted accepted, non-UTC rejected. | Local validation, no DTO change. Sol high. **Resolved**. |
| AUD-005 Dataset P2 | QA-ING-01: malformed rows yield accurate rejection reports and no invented date. `MappedCsvDatasetProvider` called `.strip()` on missing cells and assigned timezone folds without validating ambiguous/nonexistent instants. | Reject malformed rows with source position/count; preserve valid rows; reject DST gaps/overlaps unless offset explicit. `test_dataset_providers.py`; two-record repository example validated/imported with missing optional fields preserved. | Adapter-only; source row numbering re-reviewed after repair. Sol medium, lead review. **Resolved**. |
| AUD-006 Privacy P1 | QA-SEC-02: restricted content must not escape via diagnostic fields. `persist_failure`/`persist_projection_failure` stored `str(error)`, potentially retaining provider echoes or credentials in workflow/outbox. | Persist bounded stage message plus error class, never exception text. Real SQL synthetic secret/body canary verifies messages omit it. | Protected diagnostic boundary; less detailed errors by design, IDs/stage/class/attempts retained. Astra high, lead review. **Resolved**. |
| AUD-007 UI correctness P1 | QA-UX-01: latest request must own state. `App.tsx` guarded context generation but not same-context filter/page requests; advisory abort allowed old replies/errors to win. | Per-effect active ownership invalidated in cleanup, plus existing context guard. Deferred reverse-order filter and pagination DOM regressions. | No contract change; applied across data regions. Sol high, lead review. **Resolved**. |
| AUD-008 API P2 | QA-API-01: accepted page input must not overflow offsets. Endpoint allowed int-max page; `(page-1)*pageSize` could wrap in data sources. | Reject offsets exceeding int range with 400; endpoint regression exercises max page/size. | Bounds local API; no expansion of query behavior. Sol high. **Resolved**. |
| AUD-009 Time semantics P2 | QA-ANA-01: date display and request interval must agree. UI displayed date-only values but initial range retained mid-day instants; editing away/back changed population. | Initial UTC day floor/ceil; exclusive end preserved at exact midnight; invalid ranges do not issue requests. DOM roundtrip regression. | UI full-day semantics, HTTP still exact half-open UTC instants. Sol high. **Resolved**. |
| AUD-010 Metrics P2 | QA-ANA-01: label the real denominator. Every metric appended “eligible”, including classified/imported and coverage/imported measures. | Exhaustive known metric caption mapping; DOM assertions distinguish imported, classified and eligible. | Presentation-only, no numerical change. Sol high. **Resolved**. |
| AUD-011 Accessibility P2 | QA-UX-01: repeated actions identifiable. Multiple “Explore signal”/“View decision” accessible names lacked row context. | Contextual names and grouped context switch; multi-row DOM assertions. | Does not prove focus/contrast/rendered accessibility. Sol high. **Resolved**. |
| AUD-012 Documentation P2 | QA-DX-02: documentation matches current behavior. SECURITY described redaction/authenticated writes as absent; dashboard doc implied completed browser QA; README denied any cost measurement. | Security boundary rewritten, costs explicitly owner-reported, browser gate corrected, quick demo path/example and this audit linked. Review against code/artifacts. | Licensing is handled separately in AUD-013. Lead. **Resolved**. |
| AUD-013 Publication P1 | QA-DX-02: owner-approved reuse/redistribution terms. No repository license or clear content boundary existed; dataset terms do not license code. | Added canonical Apache-2.0 and CC BY 4.0 texts, scope/attribution guidance, package metadata, third-party notices, contribution terms, and an ignore rule for internal planning material. Direct links and hashes for that material were removed from public documentation and manifests. | Third-party and provider restrictions remain separate. Owner choice implemented. **Resolved**. |
| AUD-014 Analytics P2 | QA-STO-03: replay-safe effective aggregates. ClickHouse legacy SummingMergeTree materialized rollups count retry inserts even when facts deduplicate. | Real isolated replay: effective detector denominator1, legacy denominator2 after identical token and3 after forced token. Existing detector view remains correct. Document nonauthoritative tables; retire/replace before any new consumer. | No current dashboard/trend consumer uses legacy rollup metrics. Avoid destructive migration without consumer/data review. Lead/Astra evidence. **Open, contained**. |
| AUD-015 Hosted boundary P1 | QA-SEC-01/DX-02: live metadata must not become public just because raw text is withheld. Dashboard reads lack user authorization; Compose shares development LOGIN credentials. | Before hosting, enforce synthetic-only read mode server-side or authenticated live authorization; use distinct principals and environment verification. | Intentionally deferred for loopback synthetic/local scope. Owner/lead future hosting task. **Open — hosted gate**, not a broken local demo. |
| AUD-016 Rendered QA P2 | QA-UX-02: responsive/focus/contrast/keyboard and Figma parity need rendered evidence. DOM and prior capture cannot establish this. | Manual/browser gate under separate authorization. Native Figma `get_design_context` blocked by Starter quota; no workaround. | User prohibits browser/desktop automation this pass. Lead. **Not assessed / blocked integration**, no product redesign. |
| AUD-017 Statistics P2 | QA-ANA-02: comparisons must establish identical evaluation protocol and method identity. `trends/comparison.py::_require_same_input` checks four corpus fields only; `backtest.py` evaluation ID omits selected detector method. Different mappings/grace/method can pass loose provenance checks. | Add protocol hash for mappings/truth/grace/coverage and method identity to a versioned report; reject incompatible input and nonfinite metrics. Acceptance: mismatched protocol cannot compare, distinct method IDs. | Frozen current reports use matching mappings/protocol and reproduce; no observed wrong current promotion. Contract/artifact versioning required; not a quick threshold change. Lead. **Open**. |
| AUD-018 Maintainability P3 | QA-AI-02: experiment presentation derives from artifact metadata. `evaluation-components.tsx` hardcodes some model/status/error/count/cost prose. Current values match frozen artifacts, but regeneration can drift. | Extend typed per-candidate metadata if needed; derive all copy; mutated-fixture DOM and contract tests. | Shared DTO/schema change; retain the closed 192-record experiment and corrected billing. Sol high identified, lead future owner. **Open**. |
| AUD-019 Reproducibility P2 | QA-DX-01: release evidence tied to a revision. `main` is unborn, all files untracked; no exact commit or remote CI run exists. | Hash baseline/final files for this pass; owner reviews initial commit/tag and runs CI before publication. Mutable runner/image tags remain disclosed. | No commit/push silently created; preserve user snapshot. Owner/lead. **Open**. |
| AUD-020 Validation P2 | QA-ING-01/API-01: required source/time/products fail before persistence. Real endpoint tests: source:null500, omitted occurredAt202/year0001, null product500. | Required source/timestamp and product-entry guards; all three now400 with zero persistence calls. | No invented dates or DTO/schema migration. Sol high, lead review. **Resolved**. |
| AUD-021 Publication P1 | QA-DX-02: public benchmark artifacts must comply with provider terms. The baseline contained provider-restricted benchmark material. | Removed the provider recordings, reports, derived fixtures, costs, runtime option, and performance claims. Replaced the demo and evaluation slot with a locally reproducible SemIf/Qwen3.5-4B run. | SemIf code is MIT; Qwen3.5-4B is Apache-2.0; weights stay outside the repository. **Resolved — provider benchmark release gate removed**. |

## Architecture decisions after review

Keep the current component split; no broker, new ETL layer, new design system or
enterprise authentication platform was justified for this milestone. PostgreSQL
is operational authority; ClickHouse is a derived read store. The independent
projector capability must stay unable to read text, even though the local combined
process and shared LOGIN are not hosted isolation. Deterministic operational facts
remain separate from semantic judgments. Active calibration routing remains deferred.

The legacy writer checksum is an audit fingerprint, not a universal canonical
serialization standard. A structural equality fallback avoids rewriting existing
records and compares actual stored content within the caller's existing privileges.
Decisions and evidence provenance remain immutable; corrections need a new run.

## Portfolio alignment and ordered remaining work

The README now leads with the product journey and no-key Docker demo. The repository
shows useful AI engineering decisions—abstention, provenance, uncertainty and
honest evaluation—rather than a larger technology checklist. It preserves the
480-record SemIf/rules/Sol demo and the closed 192-record Mini experiment. Owner billing
is $0.39 and 477,777 tokens; the linear 480 estimate is $0.975 (displayed $0.98), not
an observed cost. SemIf has no model-provider API charge; hardware and electricity
are not included. Human-gold labels and calibrated quality are still absent.

1. **Repository release:** create an initial reviewed commit and run CI on that
   revision. No push or publication occurred here.
2. **Presentation verification:** browser/manual responsive, keyboard, focus,
   contrast and theme checks; export honest screenshots once permitted. Figma
   parity awaits quota/access. A prior capture is not current QA.
3. **Data/AI:** finish human labels, adjudication and calibration using the reserved
   splits; run held-out evaluation. Do not resume the closed paid experiment.
4. **Analytical hardening:** version comparison protocol/method identity, then retire
   unused retry-unsafe rollups. Preserve deduplicated detector inputs.
5. **Hosted scope, only if requested:** choose synthetic-only public mode or an
   authenticated live service; verify principals, retention, secrets and deployment
   boundaries in that environment.
6. **Optional polish:** derive experiment prose from typed artifact fields.

No next major feature is started automatically. Internal planning material remains
outside publication. Audit execution evidence is in
[execution-plan.md](execution-plan.md) and
[verification-report.md](verification-report.md).
