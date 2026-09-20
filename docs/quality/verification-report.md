# Verification report — 2026-09-20

Scope: current-source local synthetic portfolio demo plus isolated persistence
failure checks. No browser/desktop automation, paid inference, developer database
reset/migration, commit, push, deployment or sharing change occurred.

## Baseline and final permitted checks

Environment: Darwin 25.6.0 arm64, 10 logical CPUs; Node 24.15.0/npm 11.12.1;
Python 3.13.3/uv 0.8.16; Ruff 0.13.2/mypy 1.18.2/pytest 8.4.2;
Docker 29.8.0/Compose 5.5.1. Host .NET absent; pinned SDK 10.0.401 container used.
The branch is `main` with no initial commit; all project paths were already untracked.

| Check | Baseline | Final evidence |
|---|---|---|
| Web Prettier/ESLint/TypeScript/build | pass | pass; Vite production build 21 modules |
| Web Vitest DOM/unit |20 pass |24 pass; reverse-completion, date roundtrip, captions/action-name coverage added |
| Worker Ruff lint/format and mypy | pass, 77 files | pass, 77 files |
| Worker pytest |95 pass |103 pass after CSV source-position follow-up |
| API locked restore/Release build | pass,0 warnings/errors | current source also built in isolated demo image |
| API formatting and test suite | build baseline established |42 passed,1 explicitly skipped optional PostgreSQL integration test,0 failed |
| Real API/Python PostgreSQL interoperability | absent | optional test executed separately:1 passed,0 skipped; reverse Python check passed |
| JSON contracts | available CI definitions |20 schemas, decision/policy manifests,9 demo +480 evaluation records,1,152 predictions,3 score reports and closed experiment validated |
| Dashboard examples/fixture parity | available CI definitions |12 example responses and invariants validated; trend/evaluation/AI-reference/SemIf/rules/Sol generators `--check` byte-identical |
| Minimal user CSV | no public minimal example |2 valid imported records; no invented product/rating/language/operational fields |
| Real PostgreSQL failure injection | serial smoke and in-memory doubles | isolated pre004 reproduction, post004 recovery, configured retries, concurrent claims, stale rollback/fencing, immutable UPDATE/DELETE denial, projector denial, safe failure canaries |
| Real ClickHouse replay | no crash/replay integration evidence | same-token and forced-token replay preserve effective facts/detector counts; legacy rollup inflation reproduced and disclosed |
| Current web/API image smoke | unconfirmed this pass | freshly built isolated Nginx/API:6 HTTP check groups,3 sources,480 records,14-answer detail; no-key/no-DB setup |
| Frontend/publishable secret hygiene | ignored environment present |4 actual local secret values compared without printing them against 310 then-current publishable files and production JS:0 matches; no private key/data output added |
| New QA harness style/types | absent |5 scripts lint/format checked; ingestion, storage, projection and HTTP harness strict type checks passed; offline performance script lint/format passed |

Counts are separate layers: the optional PostgreSQL test is not counted as passed
in the ordinary API suite. Fake-store endpoint tests do not substitute for SQL.
Remote GitHub Actions was not run: the new isolated regression job is checked-in
workflow source, not evidence of a successful remote run.

## Reproduction commands

From `apps/web`: `npm run format:check`, `npm run lint`, `npm run typecheck`,
`npm test`, `npm run build`.

From `services/decision-worker`: `.venv/bin/ruff check .`,
`.venv/bin/ruff format --check .`, `.venv/bin/mypy src tests`, `.venv/bin/pytest`.
For a fresh environment first run `uv sync --locked`.

API tooling on this host, from the repository root:

```sh
mkdir -p /tmp/feedback-intelligence-nuget-cache
docker run --rm -v "$PWD:/work" \
  -v /tmp/feedback-intelligence-nuget-cache:/root/.nuget/packages -w /work \
  mcr.microsoft.com/dotnet/sdk:10.0.401 \
  dotnet restore services/api/FeedbackIntelligence.sln --locked-mode
```

Use the same container/mount prefix with `dotnet format
services/api/FeedbackIntelligence.sln --no-restore --verify-no-changes` or
`dotnet test services/api/FeedbackIntelligence.sln --configuration Release --no-restore`.

Isolated integration/performance commands from repository root:

```sh
services/decision-worker/.venv/bin/python scripts/quality_storage_check.py
services/decision-worker/.venv/bin/python scripts/quality_ingestion_check.py
services/decision-worker/.venv/bin/python scripts/quality_projection_check.py
services/decision-worker/.venv/bin/python scripts/quality_demo_check.py
services/decision-worker/.venv/bin/python scripts/quality_performance.py
uv run --locked --script scripts/validate_contracts.py
uv run --locked --script scripts/validate_dashboard_examples.py
python3 scripts/build_trend_dashboard_fixture.py --check
python3 scripts/build_evaluation_dashboard_fixture.py --check
python3 scripts/build_ai_dashboard_fixture.py --check
python3 scripts/build_ai_reference_labels.py --check
```

The three database scripts require already installed `postgres:18-alpine`,
`clickhouse/clickhouse-server:25.8` and SDK 10.0.401 images as applicable. They use
unique disposable containers, loopback ports and no application `.env`/existing
DSN. The ingestion harness uses the restored cache above. The demo script builds
unique image tags and an isolated network; it removes its own containers/network/tags.
Shared Docker build caches are retained. CI now runs the three database regressions.

## Acceptance outcomes

| QA requirement | Outcome and evidence |
|---|---|
| QA-ING-01 |Pass for supported CSV/synthetic/Olist fixtures. CSV suite 18 tests includes malformed counts/logical row positions/DST; minimal example 2 records imported. No general JSON/ETL upload platform claimed. |
| QA-ING-02 |Pass for tested Python/API duplicate/conflict paths. `quality_ingestion_check.py`: API→Python and Python→API, numerical/key-order/UTC equivalence, changed body conflict, two jobs. Historical fingerprints unchanged. |
| QA-ING-03 |Pass: explicit null/omitted operational timestamps accepted; non-UTC rejected. Missing required occurredAt/source and null product entries400 before persistence. |
| QA-ING-04 |Pass at provider/event unit layer: order-level multi-product relation retained; no fabricated product-specific attribution. |
| QA-STO-01 |Pass real SQL: concurrent claim uniqueness, stale token failure, final-attempt recovery and active owner preservation. |
| QA-STO-02 |Pass real SQL: stale finalization rolls back all inserted decisions/answers/outbox; valid transaction commits; immutable decision/answer mutation denied. Review-label/audit immutability also statically inspected, not populated/mutated by this harness. |
| QA-STO-03 |Verified with limitation: replay and acknowledgement fencing tested independently; no coordinated two-process kill between PostgreSQL/ClickHouse. Effective facts/detector cohorts reconcile; legacy rollups fail and remain nonauthoritative (AUD-014). |
| QA-AI-01 |Pass policy/event/service tests: uncalibrated raw probabilities never become eligible. Calibration itself intentionally deferred; zero facts is valid. |
| QA-AI-02 |Pass for frozen provenance/reproducibility, explicit AI-reference disclosure and closed 192 Mini subset. No paid/live provider availability or human-quality measurement performed. Hardcoded copy drift remains AUD-018. |
| QA-ANA-01 |Pass tested metric denominators, dates, paging and evidence continuity. UTC day controls map to consistent half-open ranges. No all-imported satisfaction claim. |
| QA-ANA-02 |Frozen evaluations reproduce; candidate still fails delay gate. General cross-report protocol/method identity insufficient (AUD-017); held-out validation not performed. |
| QA-SEC-01 |Pass restricted table and new content-comparison function denied to projector; live API bodies/title/excerpt withheld. No user-authenticated hosted evidence boundary exists (AUD-015). |
| QA-SEC-02 |Pass scoped redaction/telemetry/failure-message canaries and known-secret bundle check. Imported YAML uses safe_load; React renders text; SQL values parameterized. Not comprehensive PII detection or security certification. |
| QA-API-01 |Pass 42 ordinary API tests +1 separately executed real PostgreSQL test; contracts/example checks; freshly built direct HTTP journey. Missing DB is503, withheld evaluation/trends remain explained; overflow400. |
| QA-UX-01 |Pass 24 DOM/unit tests, including same-context reverse completion, existing demo/live isolation and restricted states. HTTP smoke traverses evidence without a browser. |
| QA-UX-02 |Not assessed in a browser by instruction. Native Figma design-context call blocked by Starter quota; account tier confirmed. No fallback capture/automation attempted. |
| QA-DX-01 |Isolated-equivalent current-source no-key web/API startup verified. Not a brand-new machine reinstall; local image/package caches existed. No remote CI run or release commit. |
| QA-DX-02 |Documentation aligned, nonaffiliation preserved, no external dataset copied. Apache-2.0/CC BY 4.0 split licensing and internal-plan exclusion are implemented. Restricted provider benchmark material was removed and replaced by a locally reproducible SemIf comparison. |
| QA-PERF-01 |Measured offline 10k stages and 100 warm requests each across 3 fixture routes; raw samples below. No production load, database latency or SLA claim. |

## Measured performance

Raw sanitized reports: [offline 10k](performance.json), [loopback HTTP](http-performance.json).
There is no before/after performance comparison; no performance optimization claim
or unsupported budget was introduced. First samples are not guaranteed cold-cache.

| Offline stage, 10k records | Subsequent median seconds (4 samples after first) |
|---|---:|
| Generation |0.4632 |
| Canonical load/import to temporary JSONL |0.3322 |
| Privacy transformation (load excluded) |0.2056 |
| Simple-rate frozen evaluation, generation included |0.8493 |
| Candidate frozen evaluation, generation included |0.9007 |

Five fresh child processes per stage; every stage's content hash was stable.
Reports retain first/subsequent timings and peak process RSS with platform units;
this is a process high-water mark, not incremental allocation. No p95 from five samples.

| Route through isolated Nginx/API,480-record fixtures | First measured ms | Warm median ms | Warm p95 ms | Response bytes |
|---|---:|---:|---:|---:|
| Overview |17.874 |0.955 |1.443 |4481 |
| Evidence page 10 |3.631 |0.783 |0.936 |5651 |
| Frozen trend report |1.753 |0.838 |1.107 |12978 |

Each route had 100 successful warm sequential requests with new HTTP connections;
p95 is nearest rank 95 of 100, including loopback/proxy/body read. Trend payload is
a frozen 10k backtest, not a fresh database query. No browser/rendering, concurrent
load, provider latency or representative analytical-query latency was measured.
Source inspection found live operational reads load full cohort record/decision
sets before in-memory filtering; ClickHouse detector view uses window deduplication.
Those paths need EXPLAIN and realistic eligible-data workloads before scale claims;
no speculative index/cache optimization was made on empty live analytics.

Final native bundle: 270,653 bytes JavaScript and 23,342 bytes CSS (uncompressed).
No measured browser runtime or network download budget is asserted.

## Licensing and publication-boundary follow-up

The owner selected Apache-2.0 for software and CC BY 4.0 for original authored
content. Canonical legal texts, scope, attribution, contribution terms, package
metadata, and third-party notices are present. The internal planning directory is
ignored by Git and Docker; it is absent from the publication candidate list and
from all three rebuilt runtime images.

Verification completed:

- JSON and XML metadata parsed; npm, Python, and .NET declarations resolve to
  `Apache-2.0`.
- `uv lock --check`, 18 dataset-provider tests, the 20-schema contract validator,
  and the web formatting check passed.
- The Python source and wheel packages built successfully; the wheel contains both
  `LICENSE` and `NOTICE` and reports `License-Expression: Apache-2.0`.
- Compose validation and web/API/worker image builds passed. Read-only image checks
  found Apache, CC BY, scope, NOTICE, and third-party files and found no internal
  planning directory.

The provider restriction recorded in the AUD-021 baseline was resolved by removing
that provider's recordings, reports, derived fixtures, and performance claims.

## SemIf replacement follow-up

The former provider integration was replaced with SemIf using the pinned
Qwen3.5-4B MLX configuration. The native Apple Silicon run completed all 480
records without an error and produced 88.1% primary-topic accuracy and 83.3%
macro-F1 against the Sol-medium AI reference. On the exact 192 records completed
by the closed GPT-5.4 Mini experiment, SemIf produced 85.9% accuracy and 80.7%
macro-F1, compared with 84.9% and 78.3% for GPT-5.4 Mini. These are synthetic,
AI-reference measurements rather than human-gold or production-quality claims.

The updated web quality gate passed formatting, lint, type checking, 24 tests,
and a production build. The API passed 42 tests with one optional Postgres test
skipped. The 20-schema contract validator accepted 1,152 predictions across
SemIf, rules, and the partial LLM experiment. Rebuilt API and web containers were
healthy, local HTTP checks passed, and browser verification confirmed that the
dashboard switches to the 480-record SemIf source and renders its comparison
metrics.

## Failures, limitations and untouched state

- Confirmed/repaired product failures are in the findings register. AUD-004 compile
  suspicion was disproved, excluded from counts.
- Host dotnet absence was overcome with the SDK container. Docker/uv cache sandbox
  permissions needed escalation; permitted reruns completed. No auto-review rejection
  remained. Initial ingestion harness used the wrong cache directory, then exposed
  a test analyzer error; both harness issues were corrected before passing.
- Native Figma quota blocked fresh design inspection. Browser visual/focus/keyboard/
  responsive/contrast checks, live provider calls, deployed TLS/auth/retention,
  telemetry collector end-to-end export and remote CI were not executed.
- Original migrations001–003, all frozen decisions/evaluation reports, human-label
  templates and policy thresholds stayed unchanged. New004/005 are
  forward migrations. Existing developer volumes were neither reset nor migrated.
- The earlier audit snapshot comparison identified 19 modified baseline files in
  the repair pass. The later licensing follow-up added the license/notice files,
  package metadata, publication checks, and Docker distribution changes described
  above. No unrelated user files were removed. Baseline/final file manifests remain
  point-in-time audit records rather than a release manifest.

Internal planning material was not part of the audit manifest and remains excluded
from repository publication.

## Readiness and delegation

| Gate | Verdict | Evidence / condition |
|---|---|---|
| Repository-ready |Blocked for release | Licensing, internal-plan exclusion, and provider-benchmark removal are implemented. A reviewed initial commit and CI run remain outstanding. |
| Local-demo-ready |Verified with explicit limitations | Current-source no-key images and HTTP journey, DOM state/metric tests pass. Rendered browser QA unexecuted; live remains uncalibrated. Existing running services were not replaced. |
| Hosted-demo-ready |Blocked | No reviewed server-enforced public synthetic-only mode or authenticated live reads; shared development credentials; deployment/browser checks absent. |

Astra high handled storage/privacy recovery, SQL fault tests, ClickHouse replay,
cross-service privilege review, isolated HTTP smoke and latency evidence. Sol high
handled API/product audit and bounded frontend/API repairs. Sol medium handled
baseline checks, CSV validation fixes, offline performance and documentation drafts.
The lead set scope/acceptance/ownership, repaired semantic ingestion, reviewed
protected changes, integrated CI/docs and made these readiness decisions. Exact
delegate model IDs were `gpt-6-astra` and `gpt-5.6-sol`; lead runtime identity could
not be independently selected/verified. No other major feature is started.
