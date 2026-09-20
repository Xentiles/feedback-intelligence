# Zero-configuration demo data

`feedback.jsonl` is a small, hand-authored dataset that exercises the canonical
feedback contract. It covers product praise and complaints, delivery, support,
returns, mixed feedback, ambiguity, missing optional context, and multi-product
orders. It is a development/demo fixture, not a benchmark or quality claim.

Every record is synthetic and has `privacy_status: uninspected` to exercise the
same privacy boundary as external data. It contains no ground-truth labels,
scenario identifiers, customer data, or model output.

Validate and profile it from `services/decision-worker`:

```sh
uv run --locked feedback-data validate synthetic
uv run --locked feedback-data profile synthetic
```
