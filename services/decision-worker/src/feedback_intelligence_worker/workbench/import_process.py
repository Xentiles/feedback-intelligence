"""Disposable parser: prepared environment, no provider/database calls or workflow state."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from typing import Any

from feedback_intelligence_worker.workbench.imports import (
    MAX_BYTES,
    MAX_PREVIEW_BYTES,
    check_preview,
    check_transfer,
    parse_upload,
)

PARSER_TIMEOUT_SECONDS = 30
PARSER_MEMORY_BYTES = 512 * 1024 * 1024


def isolated_parse(content: bytes, filename: str, sheet: int) -> dict[str, Any]:
    if len(content) > MAX_BYTES:
        raise ValueError("Upload exceeds the configured byte limit")
    # Do not inherit provider, database, broker or installation credentials.
    allowed = ("PATH", "LANG", "LC_ALL", "PYTHONPATH")
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    for key in ("WORKBENCH_MAX_UPLOAD_BYTES", "WORKBENCH_MAX_RECORDS", "WORKBENCH_MAX_TEXT_CHARS"):
        if key in os.environ:
            environment[key] = os.environ[key]
    with tempfile.TemporaryFile() as output:
        with subprocess.Popen(
            [sys.executable, "-m", __name__, filename, str(sheet)],
            stdin=subprocess.PIPE,
            stdout=output,
            stderr=subprocess.DEVNULL,
            env=environment,
            close_fds=True,
        ) as process:
            try:
                process.communicate(content, timeout=PARSER_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise ValueError("Upload parsing exceeded 30 seconds; split the file") from None
        if output.tell() > MAX_PREVIEW_BYTES:
            raise ValueError("Parsed preview transfer exceeds 64 MiB; split the file")
        output.seek(0)
        if process.returncode not in (0, 2):
            raise ValueError("Upload exceeded parser resources; split the file or remove columns")
        try:
            response = json.load(output)
        except (ValueError, UnicodeError):
            raise ValueError(
                "Upload parser could not complete; retry with a smaller file"
            ) from None
        if process.returncode == 2:
            raise ValueError(response["error"])
        check_preview(response)
        return dict(response)


def main() -> None:
    # Linux Docker provides a real per-child address-space ceiling. Native macOS
    # has timeout/structure/preview limits; no unsupported RSS guarantee is made.
    if sys.platform == "linux":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (PARSER_MEMORY_BYTES, PARSER_MEMORY_BYTES))
    try:
        result = parse_upload(sys.stdin.buffer.read(MAX_BYTES + 1), sys.argv[1], int(sys.argv[2]))
        check_transfer(result)
    except MemoryError:
        raise SystemExit(3) from None
    except ValueError as error:
        json.dump({"error": str(error)}, sys.stdout)
        raise SystemExit(2) from None
    except Exception:
        # No exception details or source text leave a failed parser.
        raise SystemExit(3) from None
    size = 0
    try:
        for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False).iterencode(result):
            data = chunk.encode("utf-8")
            size += len(data)
            if size > MAX_PREVIEW_BYTES:
                raise SystemExit(3)
            sys.stdout.buffer.write(data)
    except MemoryError:
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
