# feedback-decision/1.0.0

`manifest.json` is the immutable, active question manifest for the first feedback
decision contract. It defines fourteen atomic `Choice`, `Score`, and `Noul`
questions and the only fields allowed in shared model state.

The schema contains no confidence thresholds. Routing thresholds belong to a
separately versioned policy and must be fitted on a calibration set. Language,
dates, arithmetic, ownership mapping, aggregation, and trends stay in ordinary
code. Changing a question's meaning, primitive, or existing option is a breaking
schema change; do not edit this manifest after recorded decisions are published.
