# Interim AI reference

This directory contains an explicitly non-human reference set for demonstrating the
evaluation pipeline while independent human annotation is in progress. Sol medium
reviewed all 480 frozen records. A second independent pass covered the prescribed
120-record subset, and Sol medium adjudicated the 57 records with disagreements.

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
