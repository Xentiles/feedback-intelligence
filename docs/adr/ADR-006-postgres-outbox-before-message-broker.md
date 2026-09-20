# ADR-006: Use a PostgreSQL outbox before a message broker

Status: Accepted; PostgreSQL job/outbox workflow implemented.

Source: Repository architecture requirements.

## Context

The initial system needs asynchronous work and recovery without a separate messaging platform.

## Decision

Start with PostgreSQL-backed processing jobs and an outbox. Derive stable work identities and implement retries and idempotent persistence/projection in the later pipeline.

## Consequences

No Kafka or other broker is introduced. PostgreSQL claims use `SKIP LOCKED`, leases,
bounded retry state, deterministic identities, and a transactional outbox. The
continuous service loop consumes pending/expired jobs and projection events. W3C
trace context stored on each job links API ingestion to worker processing across
this asynchronous boundary. Queue-age and projection-lag metrics remain future work.
