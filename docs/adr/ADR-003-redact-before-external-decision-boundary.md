# ADR-003: Redact before the external decision boundary

Status: Accepted; deterministic worker boundary implemented.

Source: Repository architecture requirements.

## Context

Real feedback may contain identifiers and confidential content; provider and telemetry boundaries must restrict exposure.

## Decision

Perform local redaction before any external decision adapter. Exclude raw and redacted feedback bodies from telemetry by default, and never copy unredacted text into analytics.

## Consequences

The worker now emits a distinct model-safe state through deterministic redaction,
rejects likely payment credentials, and tests planted canaries against outbound
serialization and allow-listed telemetry. Broader entity detection, restricted
database roles, retention controls, and evaluation on representative private-data
fixtures remain required before production use.
