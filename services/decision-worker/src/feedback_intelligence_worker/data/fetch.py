"""Explicit dataset acquisition commands, separate from normalization/import."""

from __future__ import annotations

from pathlib import Path

import kagglehub

from feedback_intelligence_worker.data.providers.olist import OLIST_HANDLE


class DatasetFetchError(RuntimeError):
    """Raised when an external dataset could not be acquired."""


def fetch_olist(destination: Path, *, force: bool = False) -> Path:
    """Download and extract the public Olist dataset into the ignored raw directory."""
    destination.mkdir(parents=True, exist_ok=True)
    try:
        downloaded = kagglehub.dataset_download(
            OLIST_HANDLE,
            output_dir=str(destination),
            force_download=force,
        )
    except Exception as error:  # KaggleHub exposes transport/auth errors from its SDK.
        raise DatasetFetchError(
            "KaggleHub could not download the public Olist dataset. You may place the files "
            f"manually in {destination}. If Kaggle requires authentication, use `kaggle auth "
            "login`, KAGGLE_USERNAME/KAGGLE_KEY, or a token in your user Kaggle config; never "
            "store credentials in this repository."
        ) from error
    return Path(downloaded)
