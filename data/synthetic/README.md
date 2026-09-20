# Generated synthetic data

[`generator-v1.yaml`](generator-v1.yaml) is the committed, versioned specification
for the deterministic retail-feedback generator. Its default seed creates 10,000
canonical records across 450 days, five source types, twelve products, sixteen
English and Swedish scenarios, and four planted temporal events.

From `services/decision-worker`:

```sh
uv run --locked feedback-synthetic generate
uv run --locked feedback-synthetic verify
```

Generation writes three files to the ignored `generated/` directory:

- `feedback.jsonl` contains only canonical `feedback-record/1.0.0` documents.
- `provenance.jsonl` maps record IDs to generator scenario and event IDs.
- `seed-manifest.json` records the seed, version, configuration checksum, output
  checksums, distributions, date range, and planted-event counts.

`verify` regenerates every artifact using the recorded seed and count, then compares
the exact bytes. Change the seed or record count with `generate --seed <n> --count
<n>`. Existing files require `--force` before replacement.

Scenario IDs, event IDs, and future ground truth must never enter canonical records
or model state. Keep generated output local unless it is deliberately reviewed as a
reproducibility artifact. The small committed dataset in [`../demo`](../demo/README.md)
remains the zero-configuration fixture.
