"""Developer command for exercising the local privacy boundary without AI calls."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from feedback_intelligence_worker.data.config import (
    SUPPORTED_PROVIDERS,
    build_provider,
    selected_provider,
)
from feedback_intelligence_worker.privacy.boundary import PrivacyBoundary
from feedback_intelligence_worker.privacy.models import PaymentDataDetectedError, RedactionKind


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feedback-privacy",
        description="Check canonical feedback against the local pre-provider privacy boundary.",
    )
    parser.add_argument(
        "provider",
        nargs="?",
        choices=SUPPORTED_PROVIDERS,
        help="Defaults to FEEDBACK_DATA_PROVIDER or synthetic",
    )
    parser.add_argument("--path", type=Path, help="Synthetic JSONL or Olist raw directory")
    parser.add_argument("--file", type=Path, help="User CSV for the csv provider")
    parser.add_argument("--mapping", type=Path, help="Versioned YAML mapping for the csv provider")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        provider_name = selected_provider(arguments.provider)
        provider = build_provider(
            provider_name,
            path=arguments.path,
            file=arguments.file,
            mapping=arguments.mapping,
        )
        source = provider.load_feedback()
        if not source.validation.is_usable:
            print("error: source dataset has blocking validation errors", file=sys.stderr)
            return 2
        boundary = PrivacyBoundary()
        counts: Counter[RedactionKind] = Counter()
        prepared_records = 0
        rejected_payment_data = 0
        for record in source.records:
            try:
                prepared = boundary.prepare_for_decision(record)
            except PaymentDataDetectedError:
                rejected_payment_data += 1
                continue
            counts.update(prepared.redactions.counts)
            prepared_records += 1
        payload = {
            "provider_id": source.metadata.provider_id,
            "records_checked": len(source.records),
            "prepared_records": prepared_records,
            "rejected_payment_data": rejected_payment_data,
            "redactions": {
                kind.value: count for kind, count in sorted(counts.items()) if count > 0
            },
            "external_calls": 0,
        }
        if arguments.as_json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print("Privacy boundary check")
            print(f"Provider:              {payload['provider_id']}")
            print(f"Records checked:       {payload['records_checked']:,}")
            print(f"Prepared records:      {prepared_records:,}")
            print(f"Rejected payment data: {rejected_payment_data:,}")
            print(f"Redactions:            {json.dumps(payload['redactions'], sort_keys=True)}")
            print("External calls:        0")
        return 1 if rejected_payment_data else 0
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
