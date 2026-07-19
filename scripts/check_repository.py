"""Fail CI on likely secrets, generated state, or oversized repository files."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024
GENERATED_SUFFIXES = {".db", ".log", ".sqlite", ".sqlite3"}
GENERATED_PARTS = {"__pycache__", "telemetry", "var"}
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*['\"][^'\"*$<{\s][^'\"]{7,}['\"]"
)


def repository_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
    )
    return [Path(item.decode()) for item in result.stdout.split(b"\0") if item]


def main() -> None:
    failures: list[str] = []
    for path in repository_files():
        if not path.is_file():
            continue
        if path.stat().st_size > MAX_BYTES:
            failures.append(f"oversized file ({path.stat().st_size} bytes): {path}")
        if path.suffix in GENERATED_SUFFIXES or GENERATED_PARTS.intersection(path.parts):
            failures.append(f"generated artifact: {path}")
        if path.parts[0] in {"docs", "tests"} or path.name == ".env.example":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if PRIVATE_KEY.search(text) or SECRET_ASSIGNMENT.search(text):
            failures.append(f"possible committed secret: {path}")
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
