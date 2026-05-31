#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
POSTGRES_REHEARSAL_ADMIN_URL_ENV = "POSTGRES_REHEARSAL_ADMIN_URL"
SKIP_RE = re.compile(r"(?P<count>\d+)\s+skipped")


def main() -> int:
    if not os.environ.get(POSTGRES_REHEARSAL_ADMIN_URL_ENV):
        print(
            f"{POSTGRES_REHEARSAL_ADMIN_URL_ENV} must be set for the CI rehearsal run.",
            file=sys.stderr,
        )
        return 1

    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_postgres_migration_rehearsal.py",
        "-m",
        "postgres_rehearsal",
        "-q",
        "-r",
        "s",
    ]
    completed = subprocess.run(
        command,
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
    )
    if completed.stdout:
        sys.stdout.write(completed.stdout)
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    if completed.returncode != 0:
        return completed.returncode

    match = SKIP_RE.search(completed.stdout)
    if match and int(match.group("count")) > 0:
        print(
            "Postgres rehearsal reported skipped tests; treating that as a CI failure.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
