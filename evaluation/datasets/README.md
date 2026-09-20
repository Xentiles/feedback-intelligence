# Evaluation datasets

`feedback-decision-1.0.0/` is the frozen 480-record annotation sample: 300
development, 80 calibration, and 100 locked-test records. Its manifest ties the
selection to exact generator, feedback, and provenance checksums and records the
stratification distribution. Exactly 120 records require a blind second pass.

The included labels file is an empty human-annotation template, not a gold dataset.
Keep human labels separate from inference output. Never tune on the locked-test
split or use model predictions or generator provenance as gold labels.
