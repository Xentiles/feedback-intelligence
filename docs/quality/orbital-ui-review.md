# Unified interface review — 2026-10-01

Development checkpoint: `v0.1.1`, on the draft workbench branch toward `v0.2.0`.
The published `v0.1.0` release remains unchanged.

## Browser evidence

The Codex in-app browser reviewed the real React interface through the
development-only `apps/web/visual-review.html` entry. It injects deterministic
showcase/workbench clients, preserving production authentication and making no
external inference requests. This entry is absent from the production build.

Captures covered 1440, 1024, 768, 390 and 320 CSS px for Overview, Signal Explorer,
decision evidence, Datasets, Classification, Runs, Results and Connections.
There was no document-level horizontal overflow at these widths. Embedded model
and detector evaluations retain horizontally scrollable tables and data
disclosures. Additional 390 px checks covered every workbench destination with
empty, loading, failed, locked, disabled and partial fixture states.

Ignored local captures are in `artifacts/orbital-ui/`, with names such as
`overview-1440.jpg`, `classification-320.jpg`, `evidence-768.jpg`,
`final-results-1440.jpg`, `ai-confirmation-390.jpg`, and
`partial-results-390.jpg`. They contain synthetic fixtures only and are not
published as proof of production analytics.

Interaction checks exercised:

- Phone menu focus on opening, Escape/focus restoration, closing after destination
  selection, 44 px menu target, sticky access while scrolling, and inert page content.
- Collapse/reopen and navigation retaining imports, edited templates and selected
  runs; the automated suite also covers preserved showcase context and filters.
- AI sample preview with explicit consent, Cancel-first modal focus, native Escape
  denial and restored trigger focus; no inference request was submitted.
- Running-run cancellation, resume and original-text-export confirmation cancellation, plus deletion
  approval/cancellation in the automated fixture tests.
- Failed sign-in returns to Connections with a fixed explanation and removes
  the token-free error flag from the address.
- Named table overflow regions receiving keyboard focus; ArrowRight scrolled the
  620 px evidence table inside a 358 px container.
- A single decorative backdrop/canvas across navigation; its frame counter
  increased from 6 to 15 without reset when changing pages. Pointer events are
  disabled on the backdrop. Lifecycle tests assert one controller and destruction.
- Reduced-motion and poster fallback renderer configurations in the browser:
  Animate was disabled, Still selected, and Flat remained available. The original
  document visibility/reduced-motion listeners were preserved in the renderer.
- Long identifiers in evidence/provenance, source information, dense evaluations,
  empty results, partial coverage and disabled actions remained readable.

The exact palette provides approximately 9.1:1 Platinum/Gunmetal text contrast,
12.2:1 Platinum/Graphite and 10.4:1 Platinum/Deep Space Blue. Orange is used for
nontext markers, not normal text. Foreground colors and font families were inspected
in browser computed styles; the rail background was transparent.

Review limits: this is one browser surface, not a cross-browser or assistive-
technology certification. A 720 CSS px reflow check, equivalent to halving a
1440 px viewport for 200% zoom, passed without horizontal overflow. Native browser
zoom could not be changed on this review surface, so an actual 200% browser zoom
check remains a manual follow-up. Reduced-motion and graphics failure were injected
renderer states; the host operating-system preference was not changed. Hidden-page
suspension was inspected in the unchanged renderer, not simulated by changing
document visibility.

## Regression and compatibility evidence

- Frontend formatting, lint, types, production build and 43 tests passed.
- API formatting and Release build passed with zero warnings/errors; 55 tests
  passed and one optional database integration test was skipped. The new callback
  test verifies a fixed, token-free failure redirect, with no external provider call.
- All 132 Python worker tests passed after checkpoint version synchronization.
- Public frozen benchmark generation check and seven publication regression tests
  passed. Model decisions, calibration gates and frozen comparison artifacts did
  not change.
- The rebuilt local Docker installation passed upload, validation, idempotent
  rules execution, prepared evidence, export and confirmed durable purge using
  disposable acceptance data.

Remote CI evidence is attached to the updated draft PR. Real owner-initiated
ChatGPT sign-in and a separately approved small inference smoke run remain the
workbench integration acceptance gate; this UI review does not close that gate.
