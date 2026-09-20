# Architecture decision records

Use ADRs for consequential decisions, their context, and trade-offs. Name files
`ADR-NNN-short-kebab-case-title.md` and include status, context, decision, and
consequences. Use a new ADR to supersede an accepted decision; retain the history.
Proposals should say **Proposed**, not imply agreement or completed implementation.

The initial records below establish the repository's public architecture. Each
record states its current implementation status.

1. [Operational and analytical stores](ADR-001-operational-and-analytical-stores.md)
2. [Decision-engine provider abstraction](ADR-002-decision-engine-provider-abstraction.md)
3. [Redact before the external decision boundary](ADR-003-redact-before-external-decision-boundary.md)
4. [Pin evaluated model versions](ADR-004-pin-model-versions.md)
5. [Synthetic-first public demo](ADR-005-synthetic-first-public-demo.md)
6. [PostgreSQL outbox before a message broker](ADR-006-postgres-outbox-before-message-broker.md)
7. [Per-decision confidence policies](ADR-007-per-decision-confidence-policies.md)
