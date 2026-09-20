#!/usr/bin/env python3
"""Check source publication paths and sizes; never print file contents.

Default: tracked and unignored working-tree files (including ignored tracked files).
--staged: exact index blobs, suitable immediately before the release commit.
This is a path/packaging gate, not a comprehensive credential or license scanner.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 50 * 1024 * 1024
REQUIRED = {
    "README.md",
    "LICENSE",
    "NOTICE",
    "LICENSE-SCOPE.md",
    "THIRD_PARTY_NOTICES.md",
    "LICENSES/CC-BY-4.0.txt",
    "MODEL_CARD.md",
    "SECURITY.md",
    ".github/workflows/ci.yaml",
    "docs/benchmark.json",
    "docs/assets/dashboard.jpg",
    "docs/assets/demo.gif",
    "docs/assets/architecture.svg",
}
PRIVATE_DIRECTORIES = {
    "Project Plan Documentation",
    "orbital-clarity-v0.4",
    ".aws",
    ".azure",
    "secrets",
    ".secrets",
    ".venv",
    "node_modules",
    "__pycache__",
    "generated",
}
PRIVATE_NAMES = {
    "DELETME.md",
    "DELETE_ME.md",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
}
PRIVATE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".safetensors", ".gguf"}


def path_problem(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        return "unsafe path"
    if PRIVATE_DIRECTORIES.intersection(path.parts):
        return "private or generated directory"
    if path.name in PRIVATE_NAMES or path.suffix in PRIVATE_SUFFIXES:
        return "credential or model-weight file"
    if path.name.startswith(".env") and not path.name.endswith(".example"):
        return "private environment configuration"
    if name.startswith("data/processed/") and name != "data/processed/README.md":
        return "local normalized data"
    if name.startswith("data/external/") and "raw" in path.parts:
        return "raw external data"
    return None


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def inventory(root, staged=False):
    entries = {}
    if staged:
        for entry in git(root, "ls-files", "--stage", "-z").split(b"\0"):
            if not entry:
                continue
            metadata, raw_name = entry.split(b"\t", 1)
            mode, oid, stage = metadata.decode().split()
            name = raw_name.decode()
            entries[name] = (mode, oid, stage)
    else:
        names = git(
            root, "ls-files", "--cached", "--others", "--exclude-standard", "-z"
        )
        for raw_name in names.split(b"\0"):
            if raw_name:
                entries[raw_name.decode()] = None
    files, problems = [], []
    for name, index in sorted(entries.items()):
        problem = path_problem(name)
        if problem:
            problems.append(f"{name}: {problem}")
            continue
        path = root / name
        if staged:
            mode, oid, stage = index
            if mode not in {"100644", "100755"} or stage != "0":
                problems.append(f"{name}: unsupported index mode or merge conflict")
                continue
            size = int(git(root, "cat-file", "-s", oid))
        else:
            if path.is_symlink() or not path.is_file():
                problems.append(f"{name}: missing or non-regular file")
                continue
            size = path.stat().st_size
        if size > MAX_BYTES:
            problems.append(f"{name}: exceeds 50 MiB source-publication limit")
            continue
        content = (
            git(root, "cat-file", "blob", index[1]) if staged else path.read_bytes()
        )
        files.append(
            {"path": name, "bytes": size, "sha256": hashlib.sha256(content).hexdigest()}
        )
    for name in sorted(REQUIRED - entries.keys()):
        problems.append(f"{name}: required publication artifact missing")
    return files, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true")
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Write a review manifest, preferably under ignored artifacts/",
    )
    args = parser.parse_args()
    files, problems = inventory(ROOT, args.staged)
    if problems:
        raise SystemExit("Publication check failed:\n" + "\n".join(problems))
    report = {
        "scope": "git_index" if args.staged else "working_tree_candidates",
        "file_count": len(files),
        "total_bytes": sum(f["bytes"] for f in files),
        "files": files,
    }
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"Publication paths pass: {len(files)} files, {report['total_bytes']:,} bytes ({report['scope']})."
    )
    print("This does not certify secret contents, redistribution rights, or remote CI.")


if __name__ == "__main__":
    main()
