# Repository checks

Run from the repository root:

```sh
uv run --locked --script scripts/validate_contracts.py
docker compose --profile '*' config --quiet
```

The Python script validates JSON Schema documents under `schemas/` and `contracts/`,
the decision and policy manifests, committed demo/evaluation records, recorded
decision fixture, and evaluation-readiness report checksums. Semantic checks bind
the policy and readiness report to the active decision schema and frozen corpus.
Its dependencies are separate from the worker runtime and pinned by the adjacent
lockfile.

Per-component install, lint, format, type, test, and build commands live in each
component README and [CONTRIBUTING.md](../CONTRIBUTING.md).

## Isolated quality checks

After `uv sync --locked` in `services/decision-worker`, run these from repository root:

```sh
services/decision-worker/.venv/bin/python scripts/quality_storage_check.py
services/decision-worker/.venv/bin/python scripts/quality_ingestion_check.py
services/decision-worker/.venv/bin/python scripts/quality_projection_check.py
services/decision-worker/.venv/bin/python scripts/quality_demo_check.py
services/decision-worker/.venv/bin/python scripts/quality_performance.py
```

The storage/ingestion/projection checks require installed PostgreSQL 18,
ClickHouse 25.8 and/or .NET SDK 10.0.401 images. The API interoperability check also
requires a locked restore in `/tmp/feedback-intelligence-nuget-cache`; see the
[exact setup and results](../docs/quality/verification-report.md). The scripts never
accept an application DSN or load `.env`: they create unique disposable resources
and remove only those resources. The demo check builds current-source images and
uses direct loopback HTTP, not a browser. Performance reports contain synthetic
counts/timings, not feedback bodies. The offline harness needs no Docker or network.

These checks do not migrate/reset existing developer volumes or exercise paid
models. CI runs the three isolated database checks in a separate job. Browser QA,
hosted authorization and production performance remain separate gates.

## Public benchmark presentation

```sh
python3 scripts/build_public_benchmark.py
python3 scripts/build_public_benchmark.py --check
```

The first command regenerates `docs/benchmark.json`, `docs/benchmark.md`, and the
marked comparison table in the root README from frozen report artifacts. The
second fails on drift and runs in CI. It verifies shared corpus, labels, schema,
and AI-reference identity and binds the partial LLM report to the closed experiment.
It makes no model calls and does not change evaluation results or human labels.

## Publication packaging and demo animation

```sh
python3 scripts/check_publication.py --manifest artifacts/publication-candidates.json
python3 scripts/check_publication.py --staged --manifest artifacts/publication-index.json
python3 -m unittest discover -s scripts -p 'test_public*.py'
```

Default mode checks tracked and unignored working files. Index mode checks exact
staged blobs, including previously tracked private paths. It is a packaging guard,
not a full secret scanner. See [release readiness](../docs/release-readiness.md).

To rebuild the labeled four-frame walkthrough, use Python with Pillow 12.3.0:

```sh
python3 scripts/build_demo_animation.py
```

The source images are the verified screenshots in `docs/assets/`. This creates a
24-second screenshot sequence, not a simulated video recording. Pillow is an
optional asset-authoring dependency and is not required by the application or CI.
