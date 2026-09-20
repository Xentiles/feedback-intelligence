# ADR-007: Use per-decision confidence policies

Status: Accepted; policy framework implemented, calibration pending.

Source: Repository architecture requirements.

## Context

Confidence is not interchangeable across decision dimensions or primitive types.

## Decision

Fit accept/review/abstain policies per decision dimension on held-out calibration data. Choice/Score use their confidence outputs; Noul uses separately calibrated positive and negative probability cutoffs.

## Consequences

The versioned policy loader and per-dimension projection eligibility exist. The
active manifest remains `awaiting_calibration`, so every demo signal is excluded
from ClickHouse. Human labels and fitted thresholds remain pending.
