# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.8.16 AS uv

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=uv /uv /usr/local/bin/uv

RUN groupadd --system worker \
    && useradd --system --gid worker --home-dir /app worker

WORKDIR /app

COPY services/decision-worker/pyproject.toml services/decision-worker/uv.lock services/decision-worker/README.md ./
COPY LICENSE NOTICE LICENSE-SCOPE.md THIRD_PARTY_NOTICES.md ./
COPY LICENSES ./LICENSES
COPY services/decision-worker/src ./src
COPY compose.yaml ./compose.yaml
COPY contracts ./contracts
COPY schemas ./schemas
COPY evaluation ./evaluation
COPY infra/postgres ./infra/postgres
COPY infra/clickhouse ./infra/clickhouse
COPY data/demo ./data/demo
COPY data/fixtures ./data/fixtures
COPY data/synthetic/generator-v1.yaml ./data/synthetic/generator-v1.yaml

RUN uv sync --locked --no-dev \
    && chown -R worker:worker /app

USER worker

ENTRYPOINT ["decision-worker"]
