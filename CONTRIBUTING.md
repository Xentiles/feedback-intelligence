# Contributing

Read the [architecture boundaries](docs/architecture.md), relevant
[architecture decisions](docs/adr/README.md), and
[quality requirements](docs/quality/qa-plan.md) before changing a component.
Explain intentional architecture changes in an ADR. Keep this foundation free of
placeholder product behavior and invented data.

## Tooling and checks

Use Node.js 24, the .NET 10 SDK selected by `global.json`, Python 3.13, and uv
(0.8.16 or newer). Commands below run from the stated directory. The root
`.editorconfig` supplies editor defaults; each stack owns its executable formatter.

| Directory | Install | Quality checks | Build / package |
| --- | --- | --- | --- |
| `apps/web` | `npm ci` | `npm run format:check` · `npm run lint` · `npm run typecheck` · `npm test` | `npm run build` |
| `services/api` | `dotnet restore --locked-mode` | `dotnet format --verify-no-changes --no-restore` · `dotnet test --no-restore --configuration Release` | `dotnet build --no-restore --configuration Release` |
| `services/decision-worker` | `uv sync --locked` | `uv run --locked ruff check .` · `uv run --locked ruff format --check .` · `uv run --locked mypy src tests` · `uv run --locked pytest` | `uv build` |
| Repository root | uv resolves the script's locked environment | `uv run --locked --script scripts/validate_contracts.py` | `docker compose --profile '*' build` |

The worker check also covers the committed data path:

```sh
cd services/decision-worker
uv run --locked feedback-data validate synthetic
uv run --locked feedback-data profile synthetic --json
uv run --locked feedback-privacy synthetic --json
uv run --locked feedback-synthetic generate --output /tmp/feedback-synthetic
uv run --locked feedback-synthetic verify --output /tmp/feedback-synthetic
uv run --locked feedback-decisions synthetic --output /tmp/feedback-decisions.jsonl --json
```

Validate Compose with `docker compose --profile '*' config --quiet`. Container
builds do not need model or database credentials. The CI workflow runs these checks
in separate frontend, API, Python, contract, and container jobs. Isolated storage and ingestion regression jobs cover implemented database
failure paths; browser and hosted-environment review remain separate checks.

Run commands and limitations are also documented in each component README.

## Dependency changes

Commit dependency manifests together with their lockfiles. Refresh deliberately:

- Web: update `package.json` and regenerate `package-lock.json` with npm.
- API: update explicit package versions and run `dotnet restore --force-evaluate`.
- Worker: update `pyproject.toml`, run `uv lock`, then `uv sync --locked`.
- Contract checker: update inline dependencies and run
  `uv lock --script scripts/validate_contracts.py`.

Run the relevant component checks after updating. Keep model/schema/policy upgrades
separate from ordinary tooling upgrades; they need measured compatibility and
evaluation evidence once implemented.

## Data and secrets

Keep real credentials in ignored local configuration. Never introduce a client-side
model key, customer records, model-generated gold labels, or unmeasured benchmark
claims. Small synthetic fixtures are welcome when required by a real test; record
their purpose and provenance. Raw external sources belong under
`data/external/*/raw/`; canonical local output belongs under `data/processed/`.
Both are ignored. Generated scratch output belongs in ignored `generated/`
directories. Dataset adapters must emit `privacy_status: uninspected`;
normalization must never be presented as redaction. External decision adapters
must accept the model-safe privacy type and must not accept canonical records or
arbitrary mappings. Privacy tests use artificial canaries only.

## Review expectations

Keep changes focused, state the problem and resulting behavior, list checks that
actually ran, and call out remaining limitations. Introduce new infrastructure only
when it has a concrete responsibility in the documented architecture. No live
deployment or provider calls are part of routine contribution checks.

## Contribution licensing

By submitting a contribution, you agree that its software portions are licensed
under Apache-2.0 and its original documentation or authored-content portions are
licensed under CC BY 4.0, consistent with
[LICENSE-SCOPE.md](LICENSE-SCOPE.md). Do not submit material you do not have the
right to license. Preserve applicable third-party notices and identify generated
provider output separately.

## Publication checks

Before the initial commit or a release, run `python3 scripts/check_publication.py`
and review the candidate files. After staging, run the same command with `--staged`
to verify the exact index. Regenerate and check the public benchmark with
`python3 scripts/build_public_benchmark.py --check`. Full instructions and current
limits are in [release readiness](docs/release-readiness.md).
