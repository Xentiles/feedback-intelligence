# API contracts

`dashboard-v1.schema.json` defines the shared read model for the dashboard journey.
ASP.NET Core owns this boundary and the web application consumes it. The versioned
read routes are:

- `GET /api/v1/dashboard/metadata?context=live|demo`
- `GET /api/v1/dashboard/trends?context=live|demo&sourceKey=...`
- `GET /api/v1/dashboard/evaluation?context=live|demo`
- `GET /api/v1/dashboard/overview?context=...&from=...&toExclusive=...`
- `GET /api/v1/dashboard/signals/{signalId}?context=...&from=...&toExclusive=...`
- `GET /api/v1/dashboard/signals/{signalId}/evidence?...&page=1&pageSize=10`
- `GET /api/v1/dashboard/evidence/{feedbackId}?context=...&decisionId=...`

The files under `examples/` document one coherent response journey, a typed trend
evaluation, and the interim SemIf-versus-Sol comparison. The descriptive demo journey is explicitly illustrative,
repository-owned synthetic content. The trend demo is generated from the checked-in
detector back-test report, and its metrics are cross-checked against its windows,
episodes, and incidents. The live examples document the current `awaiting_calibration`
behavior: operational processing counts remain visible, analytical values are null,
and restricted evidence title, body, and excerpt are null.

The evaluation demo is generated from the checked-in 480-record score report and
labels Sol medium as an AI-reviewed reference rather than human gold. Its live
counterpart exposes no reference or scores while human annotation is incomplete.

Validate the examples and their cross-response invariants from the repository root:

```sh
uv run --locked --script scripts/validate_dashboard_examples.py
```

The validator checks every dashboard example against `dashboard-v1.schema.json`, then verifies
stable source, filter, signal, feedback, and decision identities; denominator rules;
demo/live identity separation; and the live evidence restriction. Trend validation
also proves exact 7/28-day windows, percentage-point and relative-change arithmetic,
detector gates, incident/result links, summary metrics, all four planted outcomes,
and the empty `awaiting_calibration` live state.

`feedback-ingestion-v1.schema.json` defines the canonical camel-case request and
receipt for `POST /api/v1/feedback`. The API verifies the caller-supplied UUIDv5
against the source identity, rejects payment-card candidates and oversized text,
and returns `202` for a newly queued job or `200` with the same job identity for an
idempotent replay. Ingestion is disabled by default for the public/read-only demo.
