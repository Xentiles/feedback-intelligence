"""Types that make the post-redaction decision boundary explicit."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from uuid import UUID

MODEL_CHANNELS = frozenset(
    {"product_review", "delivery_survey", "support_ticket", "return_feedback", "site_feedback"}
)
_MODEL_LANGUAGE = re.compile(r"[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-[A-Z]{2}|-[0-9]{3})?")


def is_model_language(value: str) -> bool:
    """Accept a bounded language/script/region tag, without private-use extensions."""
    return _MODEL_LANGUAGE.fullmatch(value) is not None


class PrivacyBoundaryError(ValueError):
    """Base error for records that cannot cross the privacy boundary."""


class PaymentDataDetectedError(PrivacyBoundaryError):
    """Raised when likely payment credentials require source-side rejection."""


class RedactionKind(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    NATIONAL_ID = "national_id"
    CUSTOMER_ID = "customer_id"
    ORDER_ID = "order_id"
    NAME = "name"
    ADDRESS = "address"


@dataclass(frozen=True, slots=True)
class RedactionSummary:
    """Counts redactions without retaining the values or positions that matched."""

    counts: Mapping[RedactionKind, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        cleaned = {kind: count for kind, count in self.counts.items() if count > 0}
        if any(count < 0 for count in self.counts.values()):
            raise PrivacyBoundaryError("redaction counts cannot be negative")
        object.__setattr__(self, "counts", MappingProxyType(cleaned))

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def to_dict(self) -> dict[str, int]:
        return {kind.value: count for kind, count in sorted(self.counts.items())}


@dataclass(frozen=True, slots=True)
class ModelSafeFeedbackState:
    """The only feedback shape permitted at an external decision boundary."""

    feedback_id: str
    redacted_text: str = field(repr=False)
    redacted_text_sha256: str
    source_provider_id: str
    language: str | None
    channel: str | None
    redactions: RedactionSummary
    privacy_status: str = "redacted"

    def __post_init__(self) -> None:
        try:
            UUID(self.feedback_id)
        except ValueError as error:
            raise PrivacyBoundaryError("feedback_id must be a UUID") from error
        if not self.redacted_text.strip():
            raise PrivacyBoundaryError("redacted text cannot be blank")
        if self.privacy_status != "redacted":
            raise PrivacyBoundaryError("model-safe state must have redacted privacy status")
        if not self.source_provider_id.strip():
            raise PrivacyBoundaryError("source provider cannot be blank")
        if self.channel is not None and self.channel not in MODEL_CHANNELS:
            raise PrivacyBoundaryError("model channel must be a canonical category")
        if self.language is not None and not is_model_language(self.language):
            raise PrivacyBoundaryError("model language must be a supported language tag")
        prefix = "sha256:"
        digest = self.redacted_text_sha256.removeprefix(prefix)
        if not self.redacted_text_sha256.startswith(prefix) or len(digest) != 64:
            raise PrivacyBoundaryError("redacted text hash must be a prefixed SHA-256 digest")
        if any(character not in "0123456789abcdef" for character in digest):
            raise PrivacyBoundaryError("redacted text hash must be lowercase hexadecimal")

    def to_decision_state(self) -> dict[str, str]:
        """Return the minimal state allowed to leave the local worker."""
        state = {"feedback_text": self.redacted_text}
        if self.language is not None:
            state["language"] = self.language
        if self.channel is not None:
            state["channel"] = self.channel
        return state

    def to_audit_dict(self) -> dict[str, Any]:
        """Return metadata safe for persistence or telemetry; never include text."""
        return {
            "feedback_id": self.feedback_id,
            "privacy_status": self.privacy_status,
            "source_provider_id": self.source_provider_id,
            "redacted_text_sha256": self.redacted_text_sha256,
            "redactions": self.redactions.to_dict(),
            "redaction_count": self.redactions.total,
        }
