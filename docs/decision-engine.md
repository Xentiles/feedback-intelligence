# Decision engine

The worker implements a provider-independent `DecisionEngine` boundary with local
SemIf, a structured-output LLM baseline, deterministic rules, and recorded-fixture
adapters. Every engine consumes only `ModelSafeFeedbackState`; canonical records
cannot be passed directly.

## Frozen schema

[`feedback-decision/1.0.0`](../schemas/feedback-decision/1.0.0/manifest.json)
defines fourteen atomic decisions: three choices, five scores, and six boolean
`Noul` questions. The manifest owns instructions, criteria, ordered rubrics, and
option meanings. Its SHA-256 hash is attached to every envelope and fixture set.
Confidence thresholds remain absent until the human-reviewed calibration split is
ready.

## Typed engine selection

`DECISION_ENGINE` and the API's `INGESTION_DECISION_ENGINE` accept `fixture`,
`semif`, `rules`, or `llm`. The worker registry constructs only those adapters and
unknown names fail before work or persistence. Requested model identity remains
part of each immutable job.

## Local SemIf backend

SemIf exposes option probabilities from an open causal language model. The adapter
maps each manifest question to SemIf options and returns the same project-owned
choice, score, and boolean decision types as every other engine. It pins:

- SemIf commit `ca3ba65f142967030ecb453346e94d6f476a69df`;
- `Qwen/Qwen3.5-4B` revision
  `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`;
- the MLX backend with deterministic 4-bit affine in-memory quantization; and
- runtime identity `semif-qwen3.5-4b-mlx-q4-851bf6e8`.

On Apple Silicon, install the optional backend and run a smoke record before a
full evaluation:

```sh
cd services/decision-worker
uv sync --locked --extra semif
uv run --locked --extra semif feedback-evaluation predict \
  --engine semif --limit 1 \
  --dataset ../../evaluation/ai-reference/feedback-decision-1.0.0 \
  --output /tmp/semif-smoke.jsonl --force --json
```

The first run downloads roughly 9 GB of BF16 weights into the Hugging Face cache.
Weights are quantized for inference and are never committed. SemIf probabilities
are conditional on the supplied options; the UI and policy must not present them
as calibrated confidence. The checked-in benchmark and demo fixture use the same
pinned 4-bit configuration because quantization can change distributions.

This integration uses SemIf's native MLX backend and therefore runs on the macOS
Apple Silicon host. The Linux Compose worker can replay the resulting fixture or
run the rules/LLM engines; it does not execute this MLX backend.

## Credential-free recorded mode

The default command replays the nine-record SemIf fixture without loading a model,
using a credential, or making a network call:

```sh
uv run --locked feedback-decisions synthetic --json
```

The fixture contains only redacted-input hashes, typed answers, and provenance. It
is integration evidence, not gold annotation.

## Deterministic rule baseline

`rules-1.0.0` applies fixed English and Swedish lexicons to the same model-safe
state and emits all fourteen typed answers:

```sh
uv run --locked feedback-decisions synthetic --engine rules --force --json
```

Its probabilities are deterministic heuristic scores and are not calibrated.

## General-purpose LLM baseline

`LlmSystemOneDecisionEngine` executes the same typed question objects through the
open System One Adapter and a dated OpenAI model snapshot. The historical
`gpt-5.4-mini-2026-03-17` experiment stopped at 192 successful records. It remains
an explicitly partial comparison and requires `OPENAI_API_KEY` for new calls.

## Refreshing the recorded fixture

After installing the SemIf extra, regenerate the credential-free fixture with:

```sh
uv run --locked --extra semif feedback-decisions synthetic \
  --engine semif --limit 9 \
  --record-fixture ../../data/fixtures/decisions/demo-semif-qwen3.5-4b-mlx-q4.json \
  --output /tmp/demo-semif-decisions.jsonl --force --json
```

Refreshing a fixture changes model evidence and must be reviewed like a model or
schema upgrade. Never edit probabilities manually.

## Output boundary

Decision envelopes retain feedback identity, schema hash, engine/model identity,
redacted-input hash, typed answers, latency, request ID, and token counts. They do
not contain original or redacted feedback text. The `policy` field remains null
until a separately versioned confidence policy is calibrated.
