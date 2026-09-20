"""Small conformance contract for replaceable dataset providers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from feedback_intelligence_worker.data.models import (
    DatasetLoadResult,
    DatasetMetadata,
    ValidationReport,
)


@runtime_checkable
class DatasetProvider(Protocol):
    """Normalize one source into canonical feedback records."""

    @property
    def provider_id(self) -> str:
        """Return the stable provider identifier."""

    def metadata(self) -> DatasetMetadata:
        """Return source provenance and statistics derived from actual source data."""

    def validate_source(self) -> ValidationReport:
        """Validate source structure, relationships, and normalized records."""

    def load_feedback(self) -> DatasetLoadResult:
        """Load canonical records plus complete validation and provenance."""
