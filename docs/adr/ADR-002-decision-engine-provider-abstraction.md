# ADR-002: Use a decision-engine provider abstraction

Status: Accepted; worker port plus SemIf, LLM, rules, and fixture adapters implemented.

Source: Repository architecture requirements.

## Context

The system must be reproducible without live credentials and support fair comparisons across engines.

## Decision

Keep model execution behind a provider-independent decision-engine boundary.
Recorded fixtures, local SemIf, a rule baseline, and an LLM baseline share decision
semantics.

## Consequences

Adapters translate the immutable manifest and typed outputs; application code owns
workflow, arithmetic, aggregation, and policy. The fixture, local SemIf,
structured LLM, and deterministic rule implementations share `DecisionEngine` and
consume only model-safe state. SemIf is pinned to one model revision and MLX
quantization configuration. Hosted LLM benchmarks remain explicit credentialed
evaluation actions.
