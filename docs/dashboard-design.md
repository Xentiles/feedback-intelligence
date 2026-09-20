# Dashboard product design specification

This is the implementation reference for the portions of the native design that
could not be authored after the Figma Starter-plan MCP quota was reached. It does
not replace or claim completion of the native Figma deliverable.

## Foundations

The interface uses Inter and a compact, technical workspace layout. Dark mode is
the default: near-black canvas, lifted charcoal surfaces, cool gray text, and a
violet accent limited to brand, selection, focus, and the primary chart. Light mode
uses the same semantic tokens and is available from the persistent header toggle.
Green, amber, red, and blue remain reserved for semantic states. Charts pair color
with labels, summary values, axis labels, and an accessible table.

| Figma semantic token | CSS variable | Purpose |
| --- | --- | --- |
| `color/background/canvas` | `--fi-color-background-canvas` | Application background |
| `color/background/surface` | `--fi-color-background-surface` | Cards and panels |
| `color/background/subtle` | `--fi-color-background-subtle` | Secondary regions |
| `color/text/primary` | `--fi-color-text-primary` | Primary text |
| `color/text/secondary` | `--fi-color-text-secondary` | Supporting text |
| `color/accent/default` | `--fi-color-accent-default` | Selection and primary actions |
| `color/accent/subtle` | `--fi-color-accent-subtle` | Selected backgrounds |
| `color/status/success` | `--fi-color-status-success` | Available or complete |
| `color/status/warning` | `--fi-color-status-warning` | Uncalibrated or insufficient |
| `color/status/danger` | `--fi-color-status-danger` | Error or restricted |
| `color/status/info` | `--fi-color-status-info` | Neutral information |

Spacing follows `4, 8, 12, 16, 24, 32, 40, 48px`; radii are `6, 10, 14px`.
Cards use borders first and restrained elevation only for a selected detail panel.

## Component mapping

| Design component | React component | Required states |
| --- | --- | --- |
| Application navigation | `AppShell`, `NavItem` | default, selected, focus |
| Presentation context | `ContextSwitch` | live, demo, disabled/loading |
| Filter toolbar | `FilterBar` | ready, unsupported dimension, loading |
| Metric card | `MetricCard` | available, unavailable, loading |
| Eligibility label | `StatusBadge` | illustrative, available, withheld, restricted |
| Time series | `TimeSeriesPanel` | ready, empty, unavailable, loading, error |
| Evidence list | `EvidenceTable` | ready, empty, loading, error |
| Evidence details | `DecisionDetail` | permitted synthetic, restricted live |
| Explanatory state | `StatePanel` | uncalibrated, insufficient, source unavailable |

## Desktop screens

### Overview — illustrative demo

- Compact top navigation: product identity, Overview/Signals, context switch.
- Persistent violet `Demo — selectable synthetic decisions` banner below navigation.
- Three-way decision-source control for SemIf, rules baseline, and Sol medium; the
  selected 480-record output drives the overview, filters, and evidence journey.
- Header light/dark control persists the selected theme locally.
- Source identity, actual fixture range, and supported filters.
- Four metric cards: imported feedback; classified records; analytical coverage;
  observed issue rate. Each shows a raw count or numerator/denominator.
- Time-series panel with a fixed 0–100% scale, grid, average guide, gradient area,
  smooth line, visible period labels, summary statistics, and a tabular disclosure.
- Observed signal list ordered by absolute descriptive change. Rows show current
  numerator/denominator, rate, comparison, and `Observed change` wording.
- Data-readiness panel explains illustrative eligibility and links to live context.

### Overview — live uncalibrated

- Same shell and filters, with `Live — connected data` identification.
- Operational counts are populated when the data stores are reachable.
- Analytical cards use an em dash and `Unavailable — awaiting calibration`.
- A full-width state panel explains that absence of eligible evidence is not
  absence of complaints and offers the explicit demo switch.
- No signal rows, percentages, zero-value chart, or positive/negative conclusion.
- An empty connected database shows `No imported feedback yet`, omits the date
  controls, and does not invent a source identity or analytical conclusion.

### Signal Explorer

- Breadcrumb back to Overview while preserving filters.
- Signal name, definition, current range, and `Illustrative scenario` status.
- Summary cards for numerator, eligible denominator, coverage, and observed delta.
- Time-series panel with topic numerator, eligible denominator, and rate; accessible
  period table directly below. An observed delta appears only with an explicit
  comparison range and both comparison counts.
- Contributing-feedback table ordered by occurrence descending and stable ID.
  Columns: date, safe excerpt/status, channel, product if supported, inclusion.
- Pagination is bounded, labeled, and resets after filter changes.

### Feedback and decision detail

- Back link preserves explorer signal and filters.
- Record identity and source metadata appear before evidence.
- Synthetic evidence body is visible only in demo. Live mode shows a restricted
  evidence panel with no empty body placeholder.
- Curated typed answers show question label, value, primitive, confidence label,
  and eligibility reason. They are not represented as independent reviews.
- Provenance lists immutable decision ID, schema, model, policy status, trace ID,
  and decision time. It excludes raw metadata, outbox payloads, and worker errors.

## Narrow adaptation

At widths below 760px, navigation wraps, metric cards form one column, filter
controls remain full-width and labeled, and tables become horizontally scrollable
inside a named region. Detail panels enter normal document flow. No information is
hidden solely to make the layout fit.

## Interaction and accessibility

- All controls use native buttons, links, labels, selects, and tables.
- Focus uses a 3px violet outline with 2px offset. Pointer targets are at least 40px.
- Context changes abort stale requests and reset filters, page, signal, and evidence.
- Filter changes reset evidence pagination. Back navigation preserves filters.
- Loading retains the page title and uses text plus skeletons. Errors name the
  failed region and expose one working retry button.
- `prefers-reduced-motion` removes nonessential transitions.

## Native Figma status

Dark dashboard capture:
[Feedback Intelligence — Dark Dashboard](https://www.figma.com/design/yjr5kUzT0Oc4aUJu918FYr?node-id=1-2)

- Captured node: `1:2`
- Source: running 480-record dashboard at the desktop breakpoint
- Includes the dark header, enlarged filter set, four metric cards, summary strip,
  and the new monthly time-series visualization
- Capture is an editable raw-frame reference; reusable component authoring remains
  in the original design-system file

File: [Feedback Intelligence — Dashboard Journey](https://www.figma.com/design/e17DkQwfrHNrZRRMUrRJRP)

- Foundations/documentation frame: `1:65`
- Navigation Item component set: `2:13`
- Native variables: 48 across `FI / Primitives` and `FI / Semantic`
- Native text styles: 8 Inter styles; elevation styles: 1
- Native metadata and render review completed for `1:65`
- Remaining components and screens: blocked by the Figma Starter-plan MCP call quota

Native Figma review does not establish that the implemented browser layout matches.
Browser visual and interaction verification remains deferred by the milestone's
no-browser-automation constraint.
