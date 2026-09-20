# Evaluation contracts

These contracts separate annotation inputs, human labels, and reproducibility
metadata. Semantic validation also checks every answer against the frozen decision
manifest because JSON Schema alone cannot derive option sets and score levels from
another manifest.

`evaluation-prediction.schema.json` is the common engine-output boundary used by
the scorer. It records successful typed answers or an explicit failure plus latency,
token, and optional measured-cost data. `evaluation-report.schema.json` describes
the generated quality/calibration report, while the readiness report makes the
incomplete human-label state machine-readable without publishing invented scores.
