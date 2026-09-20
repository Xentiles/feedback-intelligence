# Evaluation reports

Generated, reproducible report artifacts belong here, linked to dataset, model,
schema, policy, runner version, and methodology. The committed readiness report is
regenerated from the annotation template and records the current incomplete state.
It contains no model-quality measurements.

Once human labels are complete, `feedback-evaluation score` produces JSON and
Markdown quality reports with per-question metrics, calibration, selective
coverage, Swedish/English slices, latency, token/cost, and explicit failure rates.
Keep local scratch output in an ignored `generated/` subdirectory and publish
reviewed results deliberately.

The committed SemIf, rule, and partial LLM reports are an interim demonstration.
Their reference labels came from Sol medium and are prominently identified as not
human gold. The LLM experiment was deliberately closed after 192 of 480 successful
records; its quality and cost values describe that subset. These reports must not
be used for policy calibration or release-quality claims.
