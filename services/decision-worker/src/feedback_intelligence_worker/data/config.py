"""Dataset provider selection from explicit arguments or environment."""

from __future__ import annotations

import os
from pathlib import Path

from feedback_intelligence_worker.data.provider import DatasetProvider
from feedback_intelligence_worker.data.providers import (
    MappedCsvDatasetProvider,
    OlistDatasetProvider,
    SyntheticDatasetProvider,
)

SUPPORTED_PROVIDERS = ("synthetic", "olist", "csv")


def find_repository_root() -> Path:
    """Find the monorepo without making installed packages depend on a fixed depth."""
    candidates = (
        Path.cwd(),
        *Path.cwd().parents,
        Path(__file__).resolve(),
        *Path(__file__).parents,
    )
    for candidate in candidates:
        directory = candidate if candidate.is_dir() else candidate.parent
        if (directory / "compose.yaml").is_file() and (directory / "contracts").is_dir():
            return directory
    return Path.cwd()


def selected_provider(explicit: str | None) -> str:
    provider = explicit or os.getenv("FEEDBACK_DATA_PROVIDER", "synthetic")
    if provider not in SUPPORTED_PROVIDERS:
        supported = ", ".join(SUPPORTED_PROVIDERS)
        raise ValueError(f"Unsupported dataset provider {provider!r}; choose one of: {supported}")
    return provider


def build_provider(
    provider_name: str,
    *,
    path: Path | None = None,
    file: Path | None = None,
    mapping: Path | None = None,
) -> DatasetProvider:
    root = find_repository_root()
    configured_path = os.getenv("FEEDBACK_DATA_PATH")
    if provider_name == "synthetic":
        source = path or (
            Path(configured_path) if configured_path else root / "data/demo/feedback.jsonl"
        )
        return SyntheticDatasetProvider(source)
    if provider_name == "olist":
        source = path or (
            Path(configured_path) if configured_path else root / "data/external/olist/raw"
        )
        return OlistDatasetProvider(source)
    if file is None or mapping is None:
        raise ValueError("CSV provider requires both --file and --mapping")
    return MappedCsvDatasetProvider(file, mapping)
