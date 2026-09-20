# Benchmarks

Reproducible benchmark predictions belong here. The checked-in SemIf prediction
file and deterministic `rules-1.0.0` file each contain 480 successful, text-free
typed outputs used by the interim Sol-medium AI-reference comparison. Their
checksums are bound into the generated score reports.

Model execution remains opt-in and outside contributor PR checks. CI regenerates
the rule predictions and re-scores both frozen engines without loading SemIf model
weights. The LLM baseline runner uses the System One Adapter and the pinned
`gpt-5.4-mini-2026-03-17` snapshot. Its closed partial artifact contains 192
successful rows and has a companion metadata file that records observed and
estimated cost with their provenance. Repetition studies and human-gold results remain Week F work. See
[evaluation design](../../docs/evaluation.md).

The SemIf run executes locally and therefore has no model-provider API charge.
Token counts describe model input work; `$0` excludes hardware and electricity.

The OpenAI experiment closed at 192/480 successful records. The owner-reported
billing observation is 477,777 tokens and `$0.39`; linear record-count
extrapolation estimates approximately `$0.98` for 480 records. Adapter usage counters remain in
the prediction/report artifacts and are explicitly separated from billed usage.
