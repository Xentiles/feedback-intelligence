# ADR-001: Separate operational and analytical stores

Status: Accepted; initial PostgreSQL and ClickHouse models implemented.

Source: Repository architecture requirements.

## Context

Canonical mutable workflow state and analytical time-series queries have different responsibilities.

## Decision

Use PostgreSQL for feedback, restricted raw text, jobs/outbox, immutable decisions, review, and audit state. Use ClickHouse for derived signal facts and aggregates; exclude raw PII.

## Consequences

The PostgreSQL lease/outbox workflow, projection ledger, deterministic ClickHouse
insert token, and text-free analytical schema are implemented. Observable lag,
retention, calibrated eligible facts, and production role credentials remain.
