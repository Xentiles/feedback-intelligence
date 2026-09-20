# Repository release readiness

This page tracks the public portfolio package separately from calibrated model
quality and hosted-service readiness. The internal planning source is excluded
from Git and Docker publication; this is a public implementation status summary.

## Ready for review

- One-command, no-key synthetic Docker demo and evidence journey.
- README screenshots, a 24-second still-frame GIF walkthrough, an exported
  architecture SVG, and a model/limitations card.
- Reproducible public JSON/Markdown benchmark and README table generated from
  frozen reports. CI checks for drift without running paid inference.
- Apache-2.0 code and CC BY 4.0 authored-content scope, with third-party notices.
- Existing component, contract, fixture-parity, and isolated integration CI jobs.

## Verified source publication — 2026-09-20

The `v0.1.0` tag identifies the single-root source-release commit. That exact
commit passed all six remote CI jobs: web, API, Python, contracts, isolated
storage, and container smoke. This is release evidence for the public source
portfolio; it is not a hosted-service readiness claim.

Pre-release checks exposed platform-dependent probability serialization, a
premature container health probe, and a stale rules report missing completeness metadata.
Probabilities now serialize at ten decimal places while decisions retain full
precision; the health probe retries temporary connection errors; the rules report
and benchmark hash were regenerated without changing predictions or scores.
Actions use Node 24 and runners are pinned to Ubuntu 24.04. The exact publication
index passed its path check, excluding internal plans, the personal design
template, credentials, raw external data, generated data and model weights.

## v0.1.0 source-release decision — 2026-09-20

The owner accepted the keyboard, contrast, theme, responsive, and cross-browser
presentation review for this portfolio release. The 2026-09-20
[security review and repairs](quality/security-review.md) records three repaired
privacy findings and fresh regression evidence; a post-fix rescan was not required
for this release. The release is source-only, so no binary or container dependency
notice bundle is claimed.

The exact candidate and staged publication checks, public benchmark drift check,
and publication regression suite passed for the `v0.1.0` release change. The tag
is assigned only after all six GitHub Actions jobs pass on the release commit.
Private configuration, internal planning files, external raw data, local model
weights, scratch credential files, binaries, and container images are excluded.

## Beyond the portfolio preview

Human labels, adjudication, calibration, and locked-test scoring remain incomplete.
The closed 192-record paid experiment stays closed. The existing trend-protocol
identity and legacy-rollup audit findings remain open. Hosted authorization,
separate database principals, TLS, and retention automation remain hosted gates.
See the [audit](quality/project-audit.md) for finding-level details.

## This checkpoint

The presentation update adds no new inference, model claims, or policy thresholds.
Its benchmark check runs entirely from committed report inputs, rejects mismatched
corpus/label/schema identities, and verifies the closed LLM report hash against its
experiment record. The historical audit reports retain their original scope and
execution dates; they are not overwritten as if all historical gates were closed.

Verification for this checkpoint:

- Public benchmark generation and `--check` pass; three regression tests reject
  mismatched labels, a changed closed LLM report, and README table drift.
- Ruff format/lint pass for the new Python generator and tests.
- New presentation links resolve, and the Git candidate inventory contains no
  internal planning directory, local `.env`, or named scratch credential files.
  This path check is not a full secret-content scan.
- The running Docker demo's SemIf overview, product-defect explorer, evidence
  trace, and model comparison were inspected at 1440 × 1000. At 390 × 844,
  navigation collapsed and reopened with Enter; the selected method was preserved.
  No browser warning/error entries were reported during these interactions.
- No runtime code changed in this checkpoint. Broader component/integration test
  evidence remains in the historical verification report and must be rerun for the
  reviewed release commit.

## Publication packaging follow-up

Run from the repository root before staging:

```sh
python3 scripts/check_publication.py --manifest artifacts/publication-candidates.json
python3 -m unittest discover -s scripts -p 'test_public*.py'
```

After reviewing and staging the intended files, inspect the exact index:

```sh
python3 scripts/check_publication.py --staged --manifest artifacts/publication-index.json
git diff --cached --stat
```

The index check reads Git blobs, so an unstaged working-copy edit cannot conceal
what will actually be committed. CI uses the same index mode. Private planning,
the personal design template, named credential files, external raw data, generated
folders, model weights, symlinks, and files over 50 MiB are rejected. The default
check includes tracked files even if a later ignore rule would exclude them.
The manifest stays local under ignored `artifacts/`; it records file hashes and
sizes, not file contents. This is not a comprehensive secret or license scan.

The animation is an explicitly labeled sequence of four verified screenshots,
not a live recording. The architecture SVG distinguishes the no-key fixture path
from optional processing and the calibration gate. Static alternatives remain in
the walkthrough and architecture document.

Fresh checks on this follow-up: 25 web tests plus formatting/lint/production build;
104 worker tests plus Ruff and mypy; seven benchmark/publication regression tests;
20 JSON Schemas, 12 dashboard examples, and fixture/benchmark parity. The containerized API run passed 42 tests with one optional PostgreSQL test
skipped. Remote CI and the
isolated database-failure suite were pending at that historical checkpoint; the
verified source-publication checkpoint above records their subsequent success.
