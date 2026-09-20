# Evaluation design

**Status: the deterministic annotation sample, readiness reporting, prediction
runner, and shared scorer exist. A 480-record local SemIf run and a closed 192-record
GPT-5.4 Mini experiment have been measured against an interim Sol-medium AI
reference; human labels and policy calibration remain pending.**

The frozen sample contains 480 records split into development (300), calibration
(80), and locked test (100). Deterministic selection covers Swedish/English, all
five sources, all sixteen generator scenarios, all four planted events, and
challenge cases. Exactly 120 examples are marked for two independent annotation
passes. The sample manifest records the exact source and output checksums. Scenario
and event provenance guided sampling only; it is absent from annotation records and
cannot serve as gold. Model outputs must not become gold labels.

Regenerate the sample only from the matching 10,000-record corpus:

```sh
cd services/decision-worker
uv run --locked feedback-synthetic generate
uv run --locked feedback-evaluation sample --force --json
uv run --locked feedback-evaluation readiness --json
```

The current readiness command exits 1 because the committed template has zero
completed annotations. It validates exact record IDs, pass counts, all fourteen
typed answers, disagreements, and adjudication before allowing calibration work.
The [annotation guide](../evaluation/annotation/feedback-decision-1.0.0/GUIDE.md)
defines the blind review process and locked-test custody.

Regenerate the checked-in machine-readable readiness report:

```sh
uv run --locked feedback-evaluation report --json
```

After a split has complete human labels, every decision engine writes the common
`feedback-evaluation-prediction/1.0.0` JSONL format and uses the same scorer:

```sh
uv run --locked feedback-evaluation score \
  --split development \
  --predictions ../../evaluation/benchmarks/generated/example.jsonl \
  --output ../../evaluation/reports/generated/example.json \
  --markdown ../../evaluation/reports/generated/example.md
```

Prediction IDs must exactly equal the requested split, engine/schema metadata must
be constant across the run, and failures must be explicit rows rather than omitted.
Locked-test scoring is rejected unless `--unlock-locked-test` is supplied. That flag
is an auditable deliberate action, not permission to tune against the test set.

Compare SemIf, the implemented deterministic rule baseline, and the implemented
System One Adapter LLM baseline using the same redaction, question semantics,
records, and scorer. Keep schema, requested/resolved model, policy, and generator
versions distinct. The local SemIf adapter pins its code, model revision, MLX
backend, and 4-bit quantization; the first
LLM configuration pins `gpt-5.4-mini-2026-03-17`. The nine-record fixture is an
integration artifact and has not been scored against human labels.

Evaluate classification quality, primitive-appropriate probability calibration,
selective risk versus coverage, language slices, consistency, latency, cost, and
failure rates. Thresholds belong to individual decision dimensions and are fitted
on calibration data, never the locked test set. The versioned aggregation policy
is currently `awaiting_calibration` with null thresholds, so routing is disabled.
`Noul` uses separate positive and negative probability cutoffs rather than an
invented confidence field.

The scorer currently produces Choice accuracy, macro-F1, per-class metrics and
confusion matrices; Score MAE and quadratic weighted kappa; Noul precision, recall,
F1, AUROC and AUPRC; Brier score, ten-bin ECE, and fixed selective-coverage points;
plus language slices, latency percentiles, tokens, optional measured cost, and
failure rates. The reproducible rule run is now part of CI. An explicit
`--allow-partial` mode is limited to AI-reference experiments; human-gold scoring
still requires a complete split. Repetition/consistency comparison and human-gold
scoring remain in the Week F benchmark milestone.

## Interim SemIf versus Sol comparison

To keep the demo useful while human review proceeds, Sol medium produced a separate
AI reference over the same 480 records. Pass 1 covered every record, pass 2 covered
the frozen 120-record double-review subset, and 57 disagreements were adjudicated.
The human annotation template remains unchanged at 0/480.

Pinned SemIf with Qwen3.5-4B, the MLX backend, and deterministic 4-bit affine
quantization completed all 480 local records without an inference error. The
run reached `0.8813` primary-topic accuracy and `0.8333` macro-F1 against the
interim Sol reference. English accuracy/macro-F1 are `0.9007`/`0.8693`; Swedish
accuracy/macro-F1 are `0.8483`/`0.7408`. Median latency was 9.577 seconds per
record and p95 was 11.498 seconds in serial-prefix mode on the 16 GB M4 MacBook
Air. The run recorded 1,515,670 input tokens and incurred no model-provider API
charge; hardware and electricity are outside that `$0` value.

On the exact 192-record subset completed by GPT-5.4 Mini, SemIf reached `0.8594`
accuracy and `0.8074` macro-F1. GPT Mini reached `0.8490` and `0.7828` on those
same records. The matched subset is the appropriate direct quality comparison;
the 480-record SemIf figures describe broader coverage.

The deterministic `rules-1.0.0` baseline completed the same 480 records without an
error and reached `0.9979` primary-topic accuracy and `0.9988` macro-F1. This near
saturation is evidence that the frozen synthetic sample is lexically simple. It is
a reason to strengthen the human-reviewed challenge set, not evidence that rules
will generalise to real feedback.

## Closed GPT-5.4 Mini experiment

The pinned `gpt-5.4-mini-2026-03-17` System One Adapter run was intentionally
closed after 192/480 successful records. Its partial primary-topic agreement with
the Sol reference is `0.8490` accuracy and `0.7828` macro-F1. These values describe
only the completed subset and are not directly equivalent to the complete SemIf and
rule results.

The project owner reported 477,777 OpenAI tokens and `$0.39` of billed usage for
the partial run. Linear extrapolation by record count gives a full-run estimate of
approximately `$0.98` (`$0.39 × 480 / 192 = $0.975`, rounded to cents). The adapter prediction rows separately report
475,295 input and 72,113 output tokens; that execution telemetry differs from the
billing observation, so the owner-reported OpenAI usage view is the source for the
published cost. The frozen [experiment metadata](../evaluation/benchmarks/feedback-decision-1.0.0/gpt-5.4-mini-2026-03-17.experiment.json)
records both values and their scope.

Reproduce the partial quality report without a provider call:

```sh
cd services/decision-worker
uv run --locked feedback-evaluation score \
  --dataset ../../evaluation/ai-reference/feedback-decision-1.0.0 \
  --predictions ../../evaluation/benchmarks/feedback-decision-1.0.0/gpt-5.4-mini-2026-03-17.predictions.jsonl \
  --split all --reference-kind ai_reference --reference-model gpt-5.6-sol \
  --allow-partial \
  --output ../../evaluation/reports/generated/gpt-5.4-mini-partial.json
```

Reproduce the checked-in comparison without a provider call:

```sh
python scripts/build_ai_reference_labels.py --check
cd services/decision-worker
uv run --locked feedback-evaluation score \
  --dataset ../../evaluation/ai-reference/feedback-decision-1.0.0 \
  --predictions ../../evaluation/benchmarks/feedback-decision-1.0.0/semif-qwen3.5-4b-mlx-q4-851bf6e8.predictions.jsonl \
  --split all --reference-kind ai_reference --reference-model gpt-5.6-sol \
  --output ../../evaluation/reports/generated/semif-vs-sol.json
```

The full report includes all fourteen decision dimensions, probability metrics,
selective coverage, language slices, token counts, and latency percentiles. It is
excluded from policy calibration and does not unlock the human locked-test split.

Trend detection has a separate detector-only synthetic evaluation under
`evaluation/trends/`. The frozen simple-rate operating point detects all four
planted incidents in seed `20260919`, with 13 alert episodes, nine unmatched
episodes, `1.0` recall, `0.3077` precision, a 7.25-day mean delay, and `0.5409`
false episodes per 100 evaluable series-days. Removing the planted event rules from
the same seed still produces nine episodes. This validates the deterministic
windows, matching, and reporting path; it does not establish generalisation or
end-to-end decision quality.

The registered Beta-Binomial candidate uses the same windows and operational gates
plus a `0.98` posterior probability threshold. It preserves `1.0` recall, improves
episode precision to `0.3636`, and lowers the false-episode rate to `0.4207`, but its
mean detection delay rises from 7.25 to 8.0 days. The generated promotion gate
therefore retains `simple_rate_change`. Both reports and the comparison decision are
committed under `evaluation/trends/`.

Recorded fixture replay runs in contributor CI without credentials. Live provider
benchmarks must be explicitly enabled in a separate protected/manual workflow.
