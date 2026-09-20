# ADR-005: Use a synthetic-first public demo

Status: Accepted; synthetic generator, credential-free decisions, and dashboard demo implemented.

Source: Repository architecture requirements.

## Context

A public portfolio should be reproducible without redistributing customer data or requiring visitors to supply provider keys.

## Decision

Use reproducible synthetic retail feedback and clearly labelled recorded decisions for the default demo. Preserve model/schema provenance and keep live inference opt-in.

## Consequences

Do not imply generated incidents happened at a real retailer. Deterministic data,
recorded SemIf decisions, and explicit local-model mode are available through worker CLIs.
The web dashboard now has a separate, persistently labelled synthetic fixture whose
eligibility and decisions are illustrative and do not write into the operational
or projection paths.
