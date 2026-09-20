# Dashboard read architecture

This milestone implements a read-only journey from overview to signal, contributing
feedback, and immutable decision detail. The presentation boundary has two explicit
contexts that share the `dashboard-v1` view-model contract:

- `live` reads operational counts from PostgreSQL and analytical facts from
  ClickHouse. With the current `awaiting_calibration` policy, analytical values are
  unavailable even when processed records exist.
- `demo` derives every metric, series point, and evidence row from the committed
  480-record Sol-medium AI-reference corpus joined back to its deterministic
  synthetic source metadata. The labels are AI reviewed, not human gold; they are
  illustrative and never enter the decision, outbox, or projection path.

Changing context resets filters, pagination, selected signals, and selected evidence.
All time ranges use UTC `occurred_at` with a `[from, toExclusive)` boundary. The
initial range is the dataset's actual extent rather than a relative recent window.

## Read surface

The versioned routes are:

- `GET /api/v1/dashboard/metadata?context=live|demo`
- `GET /api/v1/dashboard/trends?context=live|demo`
- `GET /api/v1/dashboard/overview?context=...&from=...&toExclusive=...`
- `GET /api/v1/dashboard/signals/{signalId}?context=...&from=...&toExclusive=...`
- `GET /api/v1/dashboard/signals/{signalId}/evidence?...&page=1&pageSize=10`
- `GET /api/v1/dashboard/evidence/{feedbackId}?context=...&decisionId=...`

`pageSize` is bounded to 50. Evidence ordering is `occurredAt DESC, feedbackId ASC`.
Filters flow unchanged from overview through explorer and evidence, including a
canonical `provider/dataset/version` source key. Metadata lists selectable sources;
an empty source has a null available range, while connection failures use structured
HTTP Problem Details rather than invented dates. Unsupported dimensions are omitted
from controls through metadata capabilities.

The current UI binds the single source selected by metadata and carries its
`sourceKey` through every drill-down request. The contract can enumerate multiple
sources, but cross-source switching is not exposed until metadata ranges and
capabilities can be refreshed as one atomic filter transition.

An empty connected database returns `source: null`, `sources: []`, and
`availableRange: null`. The frontend presents a neutral empty-storage state with
zero operational records and no date filters, without fabricating a dataset identity.

## Metric semantics

Record, decision-run, typed-answer, job, and analytical-fact counts are separate.
Rates count distinct feedback records once. A zero numerator with a positive eligible
denominator is `0`; a zero eligible denominator is `null` with an unavailable reason.
No model probability is described as probability of correctness.

| Metric | Numerator | Denominator | Eligibility |
| --- | --- | --- | --- |
| Imported feedback | Distinct feedback records | n/a | Canonical records in range |
| Classified feedback | Distinct feedback with selected immutable decision | Imported feedback | A completed decision exists |
| Analytical coverage | Distinct feedback eligible for at least one displayed metric | Imported feedback | Versioned policy accepted the metric |
| Topic rate | Distinct eligible feedback assigned the topic | Distinct feedback eligible for topic | Topic dimension only |
| Observed issue rate | Distinct AI-reference demo records carrying at least one derived issue signal | Distinct filtered AI-reference records | Demo only; synthetic and never presented as human-gold or calibrated live quality |

The current live projector produces no facts because thresholds are uncalibrated.
The UI therefore shows processing counts and `Analytics withheld`, never `0%` or
`no issues detected`. Descriptive fixture changes are labelled `Observed change`;
statistical significance is outside this milestone.

The trend route is independent of the selected descriptive dashboard range. It
uses fixed adjacent UTC windows: current `[T-7d,T)` and baseline `[T-35d,T-7d)`.
It returns integer numerators and denominators, pooled rates, percentage-point and
relative changes, versioned thresholds, incident matches, and alert-episode quality
metrics. The demo response is generated from the frozen 10,000-record synthetic
back-test. `TREND_ALGORITHM` selects either the promoted simple-rate fixture or the
Beta-Binomial candidate fixture; the latter exposes its posterior probability and
prior configuration. Live returns `awaiting_calibration` with no trend values.

## Evidence and privacy

Live analytical queries deduplicate `projection_id` explicitly and never use
ClickHouse `source_type` as dataset identity; that column is the feedback channel.
Source identity comes from PostgreSQL provider, dataset, and version fields.

Live evidence responses expose allow-listed record metadata, curated typed answers,
and immutable schema/model/policy/trace provenance. They do not expose raw metadata,
outbox payloads, worker errors, or restricted feedback text. Until an authorized
redacted evidence boundary exists, live evidence text is returned as restricted.

## Figma and code mapping

Dark dashboard capture: [Feedback Intelligence — Dark Dashboard](https://www.figma.com/design/yjr5kUzT0Oc4aUJu918FYr?node-id=1-2).
Node `1:2` is a pixel-accurate capture of the running 480-record overview, including
the dark semantic palette, expanded filters, metric cards, and time-series design.
It is a captured editable frame rather than a component-library implementation.

Native design file: [Feedback Intelligence — Dashboard Journey](https://www.figma.com/design/e17DkQwfrHNrZRRMUrRJRP).
The foundations frame is `1:65` and the Navigation Item component set is `2:13`.
The Figma Starter-plan MCP quota then blocked remaining screen authoring. The exact
status, CSS mapping, and implementation reference are in
[`dashboard-design.md`](dashboard-design.md); the incomplete native file is not
represented as a finished design. Frontend CSS variables mirror the completed Figma
semantic color, spacing, radius, and typography tokens.

## Verification boundary

The existing Figma capture records earlier composition intent. It is not fresh
visual verification of the current build. DOM tests cover rendering and state
transitions. Browser verification of the dark default, light-mode transition,
480-record metrics, expanded filters, focus order, responsive layout and the
15-period chart remains a separate gate. No browser automation was allowed in
the 2026-09-20 audit; native Figma inspection was blocked by the Starter-plan quota.
