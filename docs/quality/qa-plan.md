# Executable audit acceptance requirements

All commands run from repository root unless specified. Allowed: shell, isolated
services, direct HTTP, DOM tests. Browser automation/desktop use is prohibited in
this pass. Preconditions use synthetic repository fixtures, never private feedback.
Execution outcomes and evidence are recorded in `verification-report.md`.

| ID / priority and risk | Preconditions, action / injection | Expected observable result | Layer / exact reference | Allowed / initial status |
|---|---|---|---|---|
| QA-ING-01 P2 unsupported/malformed CSV | Minimal mapped CSV, missing cells, extra cells, missing optional columns/values, DST ambiguous/nonexistent local time | Valid rows retained; rejected row counts and row numbers correct; no invented timestamp/product/rating/language | worker `tests/test_dataset_providers.py`, `.venv/bin/pytest tests/test_dataset_providers.py` | yes / baseline incomplete |
| QA-ING-02 P1 duplicate identity | Same canonical feedback via Python/API, reordered metadata then changed body | One job; semantic duplicates accepted; changed content explicit conflict | PostgreSQL/API integration, `scripts/quality_storage_check.py` where covered | yes / known cross-language gap |
| QA-ING-03 P2 null context | POST non-null operational context with null timestamps | 202, no invented delivery date | API `IngestionEndpointTests` | yes / known failure |
| QA-ING-04 P2 attribution | Olist fixture with multi-product order | One feedback record, relation list retained, no unsupported product-specific fact | worker `test_dataset_providers.py`, `test_storage_events.py` | yes / baseline unit pass |
| QA-STO-01 P1 lease integrity | Unique disposable Postgres; concurrent claims, expired owner and final attempt | One current owner; stale completion rolls back; exhausted work dead; active lease unaffected | new `scripts/quality_storage_check.py` | yes / missing baseline integration |
| QA-STO-02 P1 atomicity/immutability | Persist known decision + outbox; inject invalid event/stale token; mutate decision | All-or-nothing transaction; mutation denied | same isolated harness | yes / missing baseline integration |
| QA-STO-03 P1 projector recovery | Isolated CH; replay same projection after insertion before acknowledgement | Effective facts/rollup count unchanged; lease fenced; no exactly-once claim | storage harness/CI serial pipeline plus direct SQL | yes / partial baseline |
| QA-AI-01 P1 eligibility | Raw answer near 1.0 with uncalibrated policy | Ineligible; zero live facts valid; states remain separate | worker `test_evaluation_policy.py`, `test_storage_events.py`, `test_worker_service.py` | yes / baseline pass |
| QA-AI-02 P1 provenance and honesty | Frozen SemIf/rules/Sol/192 Mini outputs and readiness report | AI agreement labelled non-human; local API cost distinguished from hardware cost; billed usage separate from adapter counters; no unmeasured benchmark claimed | fixture generator `--check`, scoring CLI, dashboard API tests | yes / pending reproduction |
| QA-ANA-01 P1 denominator/time | historical demo, empty/live and filtered ranges | Distinct unavailable vs zero; consistent dates/counts/eligibility, bounded evidence population | API dashboard tests + web DOM tests | yes / partial baseline |
| QA-ANA-02 P2 statistical comparison | Frozen candidate vs simple report; incompatible reports | Reproducible synthetic-only metrics; reject mismatched evaluation populations; no held-out claim | worker `test_trends_backtest.py`, `test_trends_statistical.py` | yes / partial baseline |
| QA-SEC-01 P1 restricted access | SET ROLE projector on disposable PG; unauthorized live evidence | SELECT restricted text denied; live API does not return body | storage integration + API tests | yes / missing baseline DB evidence |
| QA-SEC-02 P1 leakage | Redaction/telemetry canaries, frontend production build | No feedback bodies/credentials in telemetry or bundle; untrusted text rendered as text | `test_privacy_boundary.py`, API telemetry tests, static bundle scan | yes / pending bundle check |
| QA-API-01 P1 build/contracts | clean SDK10 build and malformed/oversized/filter requests | Build succeeds; 400/401/413/429/503 as designed; stable DTOs and bounded SQL parameters | `dotnet test services/api` in SDK container, contract scripts | yes / baseline compile suspect |
| QA-UX-01 P2 state/continuity | DOM demo/live switch; overview→signal→evidence; delayed requests | No stale-context data, filter continuity, loading/empty/restricted/error states and accessible labels | `cd apps/web && npm test` | yes / baseline 20 pass |
| QA-UX-02 P2 rendered quality | Existing Figma references + actual browser keyboard/contrast/responsive checks | Design consistency and usable focus/viewport behavior | manual browser gate; native Figma only if available | browser prohibited / not assessed |
| QA-DX-01 P1 fresh local demo | No model credentials, existing supported container images | README start path serves coherent synthetic dashboard; storage optional | isolated Compose or image HTTP smoke; README review | yes / pending |
| QA-DX-02 P1 publication | README/SECURITY/datasets/license/media/provider inventory | Nonaffiliation explicit, measured/deferred distinguished, reuse terms owner-approved, third-party terms recorded | documentation and provider-terms review | repository licenses selected; Jev benchmark material removed |
| QA-PERF-01 P2 scale | 10k synthetic records, repeat same command with environment/sample counts | Observed timings/resource limits reported; distinguish first/warm and fixture from DB/model work | `scripts/quality_performance.py` planned | yes / unmeasured baseline |

Full worker suite: `cd services/decision-worker && .venv/bin/pytest`.
Web suite: `cd apps/web && npm run format:check && npm run lint && npm run typecheck && npm test && npm run build`.
Contracts: `uv run --locked --script scripts/validate_contracts.py` and
`uv run --locked --script scripts/validate_dashboard_examples.py`.
No test double substitutes for a real SQL failure-injection requirement.
