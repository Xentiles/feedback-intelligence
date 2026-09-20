# Decision contracts

`decision-envelope.schema.json` defines provider-independent answers and their
schema/model/execution provenance. `decision-fixture-set.schema.json` defines
credential-free recordings keyed by the hash of the redacted input. Neither
contract permits a feedback body.

`Choice` and `Score` retain distributions plus confidence. `Noul` retains only its
yes probability. The `policy` field is explicitly null until a separately versioned,
calibrated routing policy is implemented; raw engine output must not imply that it
is accepted for aggregation.

Keep result contracts separate from the question definitions in
[`schemas/feedback-decision`](../../schemas/feedback-decision/README.md).
The worker implements local SemIf, deterministic rules, an opt-in hosted LLM
baseline, and fixture replay against these contracts.
