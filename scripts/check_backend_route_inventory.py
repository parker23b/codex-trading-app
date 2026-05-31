#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.route_inventory import (  # noqa: E402
    render_backend_api_routes_markdown,
    validate_route_inventory,
)


DOC_PATH = REPO_ROOT / "docs" / "backend-api-routes.md"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the checked-in backend route inventory and route docs."
    )
    parser.add_argument(
        "--write-docs",
        action="store_true",
        help="Rewrite docs/backend-api-routes.md from the checked-in manifest.",
    )
    args = parser.parse_args()

    errors = validate_route_inventory()
    if errors:
        print("Backend route inventory check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    rendered = render_backend_api_routes_markdown()
    current = DOC_PATH.read_text()
    if current != rendered:
        if args.write_docs:
            DOC_PATH.write_text(rendered)
        else:
            print(
                "docs/backend-api-routes.md is out of date. "
                "Run `python3 scripts/check_backend_route_inventory.py --write-docs`.",
                file=sys.stderr,
            )
            return 1

    print("Backend route inventory check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
