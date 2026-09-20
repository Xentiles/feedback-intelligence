# Feedback Intelligence — model and limitations card

## Intended use

An independent portfolio demonstration of typed feedback classification, explicit
uncertainty, deterministic analytics, and evidence navigation. The committed demo
uses synthetic retail feedback. It is suitable for inspecting the implementation
and reproducing recorded evaluations, not for automated customer decisions.

## Evaluated configuration

| Component | Frozen identity |
| --- | --- |
| Decision schema | `feedback-decision/1.0.0`, fourteen questions |
| Local engine | `semif-qwen3.5-4b-mlx-q4-851bf6e8` |
| SemIf source | `ca3ba65f142967030ecb453346e94d6f476a69df` |
| Base model revision | Qwen3.5-4B, `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` |
| Local inference | Apple Silicon, MLX, 4-bit quantization |
| Deterministic baseline | `rules-1.0.0` |
| General-purpose comparison | `gpt-5.4-mini-2026-03-17`, closed partial experiment |
| Interim reference | `gpt-5.6-sol`, medium reasoning; AI labels, not human gold |
| Aggregation policy | `aggregation-policy/1.0.0`, uncalibrated; thresholds remain null |

The local demo replays recorded output; opening it does not run these models.
Installing the optional SemIf dependencies and model weights is a separate local
inference workflow. See [decision engine](docs/decision-engine.md).

## Evaluation population and results

The reference contains 480 selected synthetic English and Swedish records, with
120 second passes and 57 adjudications by the AI review workflow. The human-label
workspace remains separate and incomplete. The generator's templates limit the
linguistic and behavioral variety of the sample.

The [generated benchmark](docs/benchmark.md) and its
[machine-readable companion](docs/benchmark.json) contain the measured agreement,
exact model identities, corpus/schema/label checksums, and source artifact hashes.
The complete SemIf and rules runs contain 480 successful records each. The LLM
experiment stopped at 192 successes; its subset must not be presented as a full,
matched head-to-head result. Do not reopen it to complete the presentation package.

Rule saturation is evidence that this synthetic task strongly rewards lexical
matching. It does not establish real-world generalization. Language slices and
probability metrics against AI labels are diagnostic; they are not human-validated
calibration. The locked human test set has not been promoted to a gold result.

## Cost and latency

The LLM experiment's $0.39 and 477,777 tokens are owner-reported billing totals.
Adapter counters are separate execution telemetry. The approximately $0.98 full-run
figure is linear extrapolation, not a completed experiment or current price quote.
Local SemIf and rules have no provider API charge; hardware and electricity are
excluded. Recorded latency comes from different execution environments and is not
a controlled throughput comparison. A zero rules timer value is not zero runtime.

## Product boundaries

- Demo eligibility is illustrative. Its 100% coverage does not imply calibrated
  production acceptance. Live analytics withhold unsupported results.
- The 15-period dashboard chart is descriptive. The separate planted-incident
  backtest evaluates the detector, not model quality or real-traffic detection.
- Regex redaction reduces known exposures but cannot guarantee removal of every
  kind of private data. Arbitrary customer data is outside the public demo scope.
- Local reads are not a hosted authorization boundary. Public hosting requires
  server-enforced synthetic-only reads or authenticated live access.

## Promotion requirements

Finish human annotation and adjudication, calibrate per-question policies on the
reserved calibration split, evaluate the locked test split, and inspect language
and failure slices before making production-quality claims. Retain model, schema,
policy, and input provenance when changing any engine. See
[evaluation design](docs/evaluation.md) and [release readiness](docs/release-readiness.md).

## Reuse

Project code uses Apache-2.0; original authored documentation uses CC BY 4.0.
Models, dependencies, provider outputs, and external datasets retain their own
terms. See [license scope](LICENSE-SCOPE.md) and
[third-party notices](THIRD_PARTY_NOTICES.md).
