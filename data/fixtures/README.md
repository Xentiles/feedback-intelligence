# Shared data fixtures

Small, non-sensitive mapping examples and, later, recorded decision outputs belong
here. The versioned CSV mapping demonstrates the generic import boundary. Adapter
unit fixtures live beside the worker tests so their source and expected failures
stay close together. Distinguish hand-authored test doubles from provider
recordings and record provenance for every recording.

Use artificial PII canaries for future privacy tests. Do not commit customer data,
credentials, or raw provider debug dumps. Gold labels belong in `evaluation/datasets`.
# Fixtures

`decisions/demo-semif-qwen3.5-4b-mlx-q4.json` contains local SemIf outputs for the
nine committed synthetic demo records. It uses `feedback-decision/1.0.0` and the
pinned `semif-qwen3.5-4b-mlx-q4-851bf6e8` runtime identity.

The fixture stores redacted-input hashes and typed decisions only. It contains no
feedback bodies, credentials, policy thresholds, or gold labels. Regenerate it only
through the documented local recording command and review model/schema provenance
before replacing it.
