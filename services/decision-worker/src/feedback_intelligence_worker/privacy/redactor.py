"""Conservative deterministic redaction for the pre-provider privacy boundary."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from datetime import date

from feedback_intelligence_worker.privacy.models import (
    PaymentDataDetectedError,
    RedactionKind,
    RedactionSummary,
)

Replacement = str | Callable[[re.Match[str]], str]

_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_NATIONAL_ID = re.compile(r"(?<!\d)(?:\d{2})?\d{6}[-+]\d{4}(?!\d)")
_CUSTOMER_ID = re.compile(
    r"\b(?P<prefix>(?i:customer\s+(?:id|number|no)|account\s+(?:id|number|no)|"
    r"kund(?:nummer|\s*id)))\s*(?:#|:|-)?\s*"
    r"(?P<value>(?=[A-Z0-9_-]*\d)[A-Z0-9][A-Z0-9_-]{3,})\b",
    re.ASCII,
)
_ORDER_ID = re.compile(
    r"\b(?P<prefix>(?i:order\s+(?:id|number|no)|order(?:nummer|\s*id)))"
    r"\s*(?:#|:|-)?\s*"
    r"(?P<value>(?=[A-Z0-9_-]*\d)[A-Z0-9][A-Z0-9_-]{3,})\b",
    re.ASCII,
)
_NAME = re.compile(
    r"\b(?P<prefix>(?i:my name is|name\s*:|jag heter|namn\s*:))\s*"
    r"(?P<value>[A-ZÅÄÖÉ][A-Za-zÅÄÖåäöÉé'-]+"
    r"(?:\s+[A-ZÅÄÖÉ][A-Za-zÅÄÖåäöÉé'-]+){0,3})"
)
_ENGLISH_ADDRESS = re.compile(
    r"\b\d{1,5}\s+[A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,4}\s+"
    r"(?i:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr|Way)\b"
)
_SWEDISH_ADDRESS = re.compile(
    r"\b[A-ZÅÄÖ][A-Za-zÅÄÖåäöÉé'-]{1,30}(?i:gatan|vägen|gränd|allén)"
    r"\s+\d{1,4}[A-Za-z]?\b"
)
_POSTAL_CITY = re.compile(r"\b\d{3}\s?\d{2}\s+[A-ZÅÄÖ][A-Za-zÅÄÖåäöÉé'-]{1,40}\b")
_PHONE_CANDIDATE = re.compile(
    r"(?<![\w])(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}(?![\w])"
)
_PAN_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_IBAN_CANDIDATE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b", re.IGNORECASE)
_CVV = re.compile(r"\b(?i:cvv|cvc|card security code)\s*(?:#|:|-)?\s*\d{3,4}\b")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DeterministicRedactor:
    """Apply a documented, local baseline without retaining matched values."""

    def redact_text(self, text: str) -> tuple[str, RedactionSummary]:
        if not text.strip():
            raise ValueError("text to redact cannot be blank")
        self._reject_payment_data(text)
        counts: Counter[RedactionKind] = Counter()
        redacted = text

        redacted = self._replace_valid_national_ids(redacted, counts)
        redacted = self._apply(
            redacted,
            _EMAIL,
            "[EMAIL]",
            RedactionKind.EMAIL,
            counts,
        )
        redacted = self._apply(
            redacted,
            _CUSTOMER_ID,
            lambda match: f"{match.group('prefix')} [CUSTOMER_ID]",
            RedactionKind.CUSTOMER_ID,
            counts,
        )
        redacted = self._apply(
            redacted,
            _ORDER_ID,
            lambda match: f"{match.group('prefix')} [ORDER_ID]",
            RedactionKind.ORDER_ID,
            counts,
        )
        redacted = self._apply(
            redacted,
            _NAME,
            lambda match: f"{match.group('prefix')} [NAME]",
            RedactionKind.NAME,
            counts,
        )
        for address_pattern in (_ENGLISH_ADDRESS, _SWEDISH_ADDRESS, _POSTAL_CITY):
            redacted = self._apply(
                redacted,
                address_pattern,
                "[ADDRESS]",
                RedactionKind.ADDRESS,
                counts,
            )
        redacted = self._replace_phones(redacted, counts)
        return redacted, RedactionSummary(counts)

    def _reject_payment_data(self, text: str) -> None:
        if _CVV.search(text):
            raise PaymentDataDetectedError(
                "Potential card security code detected; remove payment data before processing"
            )
        if any(_passes_luhn(_digits(match.group())) for match in _PAN_CANDIDATE.finditer(text)):
            raise PaymentDataDetectedError(
                "Potential payment card number detected; remove payment data before processing"
            )
        if any(_valid_iban(match.group()) for match in _IBAN_CANDIDATE.finditer(text)):
            raise PaymentDataDetectedError(
                "Potential IBAN detected; remove payment data before processing"
            )

    def _replace_valid_national_ids(
        self,
        text: str,
        counts: Counter[RedactionKind],
    ) -> str:
        def replace(match: re.Match[str]) -> str:
            if not _valid_swedish_identity_number(match.group()):
                return match.group()
            counts[RedactionKind.NATIONAL_ID] += 1
            return "[NATIONAL_ID]"

        return _NATIONAL_ID.sub(replace, text)

    def _replace_phones(
        self,
        text: str,
        counts: Counter[RedactionKind],
    ) -> str:
        def replace(match: re.Match[str]) -> str:
            candidate = match.group().strip()
            digit_count = len(_digits(candidate))
            if digit_count < 7 or digit_count > 15 or _ISO_DATE.fullmatch(candidate):
                return match.group()
            counts[RedactionKind.PHONE] += 1
            return "[PHONE]"

        return _PHONE_CANDIDATE.sub(replace, text)

    def _apply(
        self,
        text: str,
        pattern: re.Pattern[str],
        replacement: Replacement,
        kind: RedactionKind,
        counts: Counter[RedactionKind],
    ) -> str:
        redacted, count = pattern.subn(replacement, text)
        counts[kind] += count
        return redacted


def _digits(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def _passes_luhn(value: str) -> bool:
    if len(value) < 10:
        return False
    total = 0
    parity = len(value) % 2
    for index, character in enumerate(value):
        digit = int(character)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _valid_swedish_identity_number(value: str) -> bool:
    digits = _digits(value)
    if len(digits) not in (10, 12):
        return False
    short = digits[-10:]
    year = int(digits[:4]) if len(digits) == 12 else 2000 + int(short[:2])
    month = int(short[2:4])
    day = int(short[4:6])
    if day > 60:
        day -= 60
    try:
        date(year, month, day)
    except ValueError:
        return False
    return _passes_luhn(short)


def _valid_iban(value: str) -> bool:
    compact = "".join(value.split()).upper()
    if not 15 <= len(compact) <= 34 or not compact[:2].isalpha() or not compact[2:4].isdigit():
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(
        character if character.isdigit() else str(ord(character) - ord("A") + 10)
        for character in rearranged
    )
    return int(numeric) % 97 == 1
