# Aggregation policies

An aggregation policy is a separately versioned companion to a frozen decision
schema. It defines how decision confidence may route answers into accepted,
review, or abstained states. A policy with `awaiting_calibration` status has no
thresholds and cannot be applied.

Thresholds must be fitted on reviewed labels and recorded with dataset and label
checksums. SemIf outputs and synthetic generator provenance are never gold labels.
