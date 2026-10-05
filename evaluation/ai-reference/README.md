# Interim AI reference

This directory contains an explicitly non-human reference set for demonstrating the
evaluation pipeline while independent human annotation is in progress. Retained
artifacts contain 480 first-pass labels, a 120-record second-pass subset and 57
adjudications, labelled as Sol medium in the historical manifest.

Reference construction includes AI-assisted template reasoning and deterministic
assembly. `work/make_sol_pass1.py` maps recognized synthetic templates to fixed
answers and writes Sol-labelled records; it makes no provider call. Retaining pass
files and hashes proves assembly reproducibility, not separately logged per-record
model inference or independent review. The same model-family and repeated-template
limitations apply. Frozen labels, manifests and measured scores remain unchanged.

The original human annotation template under `evaluation/datasets/` remains empty
and unchanged. These AI labels must not be used to calibrate the production policy,
unlock human test claims, or describe model quality against human gold.

Regenerate the assembled records, labels, and manifest:

```sh
python scripts/build_ai_reference_labels.py
python scripts/build_ai_reference_labels.py --check
```

The source pass files are retained so the assembly and disagreement process remain
auditable. The manifest records their hashes and the resulting label checksum.
