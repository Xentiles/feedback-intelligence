# ADR-004: Pin model versions for evaluated releases

Status: Accepted; SemIf code, model weights, quantization, and fixture identities are pinned.

Source: Repository architecture requirements.

## Context

Moving model aliases can change outputs and invalidate calibrated confidence policies.

## Decision

Use an explicit evaluated model revision and retain requested/resolved model
provenance. The local SemIf configuration pins its source commit, Qwen weight
revision, MLX backend, and 4-bit quantization; do not benchmark a moving alias.

## Consequences

Promote model and policy changes only after frozen-corpus evaluation and calibration
review. The adapter accepts only the frozen runtime identity, and envelopes retain
requested and resolved model IDs. Interim results measure agreement with an AI
reference and do not establish human quality.
