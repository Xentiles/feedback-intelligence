# Results inspection review — 2026-10-02

Development checkpoint: `v0.1.5`, on the draft workbench branch toward `v0.2.0`.
The published `v0.1.0` release and frozen recorded comparisons remain unchanged.

## Browser evidence

The Codex in-app browser exercised the real React interface with deterministic
clients through the development-only `visual-review.html` entry. The production
build excludes this entry. No external inference or OAuth sign-in was performed.

The dense fixture contains 10,000 successful records across 450 observed UTC dates.
It produces 15 monthly chart periods, retains daily counts and uses a 280 px chart
height. Captures at 1440, 1024, 768, 390 and 320 CSS px showed the chart inside its
panel and no document-level horizontal overflow. A separate 720 CSS px reflow
check passed. At 320 px a focused preview measured left 16/right 304 and remained
within the viewport; the modal inspector also wrapped long snapshot hashes.

Interaction checks exercised:

- Arrow/Home/Enter period selection, pinned details, Escape and trigger focus
  restoration; period drill-down applied both UTC dates, reset evidence pagination
  and focused the evidence heading below the sticky menu.
- Missing sentiment selection produced 4,000 matching records and an explicit
  active chip. Run-wide menu counts remained available beyond the first page.
- Record details on phones, wrapped identifiers, ratings/metadata, redactions and
  recorded rule evidence.
- Showcase metric inspection, period previews with rate and eligible denominator,
  explicit period filters, and frozen evaluation inspection showing the 192/480
  boundary and AI-reference rather than human-gold context.
- Results empty, loading, failed, partial and session-failure fixtures, including
  retry controls; model catalog failure/empty states on Classification.
- Run actions measured a 24 px gap below Engine and a 16 px wrapping action gap.
  Connections sign-in and Manage usage actions also measured a 16 px gap.
- One decorative canvas remained mounted across views. Existing motion, graphics
  fallback and navigation verification is recorded in the earlier interface review.

Ignored local synthetic captures are in `artifacts/results-inspection/`, including
`dense-chart-{width}.jpg`, `record-inspector-320.jpg`, state captures,
`showcase-evaluation-1440.jpg`, and `final-period-inspector-{1440,320}.jpg`.

Limits: this is one browser surface, not a cross-browser, screen-reader or touch
device certification. Native 200% browser zoom was unavailable; 720 CSS px reflow
is an approximation, not certification of actual zoom. Hover logic is exercised
in component tests; real-browser interaction evidence uses focus, click and
keyboard selection. Reduced-motion/graphics fallback and lifecycle checks from
the earlier review remain historical evidence, not a newly repeated OS test.

## Regression and runtime evidence

- Frontend formatting, lint, type checking, 97 tests and production build passed.
  Tests cover run switching, stale responses, removed selections, retries, filters,
  missing/literal values, inspectors, navigation, focus return and legacy responses.
- Worker lint, formatting, types and 143 tests passed. Added regressions cover
  reserved topic IDs, UTC boundaries, combined/missing filters, full-run facets,
  clamped pagination, prepared exports, method identity and topic trend rejection.
- Frozen public benchmark generation and seven publication regressions passed.
- The rebuilt local Docker workbench passed upload → validation → idempotent rules
  run → prepared evidence → export → durable purge using disposable acceptance data.
- A read-only check of the real saved 10,000-record run returned all five facet
  totals as 10,000, 450 daily periods and page 200 when page 999 was requested.
  A single-day UTC filter and export both returned 23 records with matching
  selection provenance and no original text. Topic-filtered trends returned HTTP 400.

Remote CI evidence is linked from the updated draft PR. No database migration,
chart dependency, paid experiment or release-tag change is part of this checkpoint.
Real owner-initiated ChatGPT sign-in and an explicitly approved small classification
run remain an independent acceptance gate; this review does not declare the
provider integration operational or the local tool ready for hosted deployment.
