# Annotation guide: feedback-decision 1.0.0

Annotate only the text, language, and channel in `records.jsonl`. Do not inspect
SemIf outputs, generator scenarios/events, ratings, operational fields, or another
annotator's answers. Those sources would bias the gold labels.

Each label row already carries the matching feedback ID and split. Add one object
to `annotations`; records with `requires_second_pass: true` require two independent
objects with passes 1 and 2. Use pseudonymous annotator IDs. Every pass must answer
all fourteen questions using the exact choices, score levels, and criteria in the
[frozen decision manifest](../../../schemas/feedback-decision/1.0.0/manifest.json).

Answer representation is deliberately smaller than model output:

```json
{
  "primary_topic": { "type": "choice", "value": "product_quality" },
  "overall_experience": { "type": "score", "value": 1 },
  "reports_product_defect": { "type": "noul", "value": true }
}
```

Choice values are option IDs, score values are integer rubric levels, and Noul
values are booleans. Human labels never include probabilities or confidence.

When the two passes differ anywhere, a third reviewer must add `adjudication` with
the final fourteen answers and a short reason. Do not overwrite either independent
pass. Calibration is blocked until all required passes and adjudications exist.

The locked-test split is assigned and frozen now, but its completed labels must be
held by the test custodian. Policy fitting may use development and calibration
labels only. Unlock the test labels once for the final evaluation of a frozen
schema, engine/model, and policy tuple.

Validate progress from `services/decision-worker`:

```sh
uv run --locked feedback-evaluation readiness --json
uv run --locked feedback-evaluation report --json
```

Exit status 1 means the structurally valid corpus is incomplete. Status 0 means all
480 records have their required human passes and all disagreements are adjudicated;
it does not by itself claim model quality.
