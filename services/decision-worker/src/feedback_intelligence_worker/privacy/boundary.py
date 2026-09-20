"""Transform canonical records into the minimal state allowed outside the worker."""

from __future__ import annotations

import hashlib

from feedback_intelligence_worker.data.models import FeedbackRecord
from feedback_intelligence_worker.privacy.models import (
    MODEL_CHANNELS,
    ModelSafeFeedbackState,
    is_model_language,
)
from feedback_intelligence_worker.privacy.redactor import DeterministicRedactor


class PrivacyBoundary:
    """Own the mandatory local transformation before any decision-engine call."""

    def __init__(self, redactor: DeterministicRedactor | None = None) -> None:
        self._redactor = redactor or DeterministicRedactor()

    def prepare_for_decision(self, record: FeedbackRecord) -> ModelSafeFeedbackState:
        return self.prepare_text(
            feedback_id=record.feedback_id,
            text=record.original_text,
            source_provider_id=record.source.provider_id,
            language=record.language,
            channel=record.channel,
        )

    def prepare_text(
        self,
        *,
        feedback_id: str,
        text: str,
        source_provider_id: str,
        language: str | None,
        channel: str | None,
    ) -> ModelSafeFeedbackState:
        """Apply the same boundary to canonical records and imported evaluation text."""
        redacted_text, summary = self._redactor.redact_text(text)
        digest = hashlib.sha256(redacted_text.encode("utf-8")).hexdigest()
        return ModelSafeFeedbackState(
            feedback_id=feedback_id,
            redacted_text=redacted_text,
            redacted_text_sha256=f"sha256:{digest}",
            source_provider_id=source_provider_id,
            language=language if language is not None and is_model_language(language) else None,
            channel=channel if channel in MODEL_CHANNELS else None,
            redactions=summary,
        )
