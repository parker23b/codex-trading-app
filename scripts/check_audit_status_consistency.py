#!/usr/bin/env python3
"""Guard the current audit/readiness closure snapshot against stale drift.

This check is intentionally explicit and conservative. It validates only the
small set of current-status claims that are easy to drift back into
contradiction:

- the current CI truth must stay anchored to the newest successful Repo Audit
  run reviewed in this closure pass;
- current-scope finding classifications must not silently regress;
- current sections must not reintroduce older failed CI runs as present truth;
- manual security actions must not be described as completed in the current
  readiness snapshot.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_STATUS = REPO_ROOT / "docs" / "audit-status.md"
READINESS = REPO_ROOT / "docs" / "readiness.md"
MATRIX = REPO_ROOT / "docs" / "spec" / "99-spec-coverage-matrix.md"

LATEST_SUCCESS_RUN_ID = "26776683955"
OLDER_RUN_IDS = ("26772490408", "26189047732")


def current_section(text: str, marker: str) -> str:
    if marker not in text:
        raise ValueError(f"Missing section marker: {marker}")
    return text.split(marker, 1)[0]


def require(text: str, pattern: str, message: str, errors: list[str]) -> None:
    if not re.search(pattern, text, re.MULTILINE):
        errors.append(message)


def forbid(text: str, pattern: str, message: str, errors: list[str]) -> None:
    if re.search(pattern, text, re.MULTILINE):
        errors.append(message)


def main() -> int:
    audit_text = AUDIT_STATUS.read_text()
    readiness_text = READINESS.read_text()
    matrix_text = MATRIX.read_text()

    audit_current = current_section(audit_text, "## Historical Remediation Slices")
    readiness_current = current_section(readiness_text, "## Historical Notes")
    matrix_current = current_section(matrix_text, "## Coverage status summary")

    errors: list[str] = []

    for text, label in (
        (audit_current, "audit-status current section"),
        (readiness_current, "readiness current section"),
        (matrix_current, "coverage-matrix current section"),
    ):
        require(
            text,
            re.escape(LATEST_SUCCESS_RUN_ID),
            f"{label} must reference current successful Repo Audit run {LATEST_SUCCESS_RUN_ID}.",
            errors,
        )
        for run_id in OLDER_RUN_IDS:
            forbid(
                text,
                re.escape(run_id),
                f"{label} must not present older run {run_id} as current truth.",
                errors,
            )

    for pattern, description in (
        (r"`Verify backend lockfiles`: passed", "Verify backend lockfiles pass status"),
        (r"`Migration and drift tests`: passed", "migration and drift pass status"),
        (r"`Postgres migration rehearsal`: passed with exactly `5 passed` and zero skips|`Postgres migration rehearsal`: exactly `5 passed`, zero skips", "Postgres rehearsal pass status"),
        (r"backend `Pytest`: passed", "backend pytest pass status"),
    ):
        require(audit_current, pattern, f"audit-status current section must include {description}.", errors)

    expected_classes = {
        "AUDIT-UI-006": "CLOSED_CURRENT_SCOPE",
        "AUDIT-LIFE-005": "CLOSED_CURRENT_SCOPE",
        "AUDIT-005": "CLOSED_CURRENT_SCOPE",
        "AUDIT-UI-002": "CLOSED_CURRENT_SCOPE",
        "AUDIT-UI-004": "CLOSED_CURRENT_SCOPE",
        "AUDIT-UI-005": "CLOSED_CURRENT_SCOPE",
        "AUDIT-DB-001": "DOCUMENTED_LIMITATION",
        "AUDIT-SEC-002": "DOCUMENTED_LIMITATION",
        "AUDIT-SEC-003": "MANUAL_SECURITY_ACTION",
        "AUDIT-DEP-001": "FUTURE_PRODUCTION_HARDENING",
    }
    for finding_id, classification in expected_classes.items():
        require(
            audit_current,
            rf"\|\s*`?{re.escape(finding_id)}`?\s*\|[^\n]*`{re.escape(classification)}`",
            f"audit-status current inventory must classify {finding_id} as {classification}.",
            errors,
        )

    forbid(
        audit_current.lower(),
        r"audit-ui-006.{0,120}(open|still open|remains open)",
        "audit-status current section must not re-open AUDIT-UI-006 without explicit new residual scope.",
        errors,
    )
    forbid(
        readiness_current.lower(),
        r"audit-ui-006.{0,120}(open|still open|remains open)",
        "readiness current section must not describe AUDIT-UI-006 as currently open.",
        errors,
    )
    forbid(
        audit_current.lower(),
        r"current ci still does not prove|does not include a successful current-workflow ci run",
        "audit-status current section must not claim current CI proof is missing.",
        errors,
    )
    forbid(
        readiness_current.lower(),
        r"current ci still does not prove|does not include a successful current-workflow ci run",
        "readiness current section must not claim current CI proof is missing.",
        errors,
    )

    require(
        audit_current.lower(),
        r"no current code-actionable p0 or p1 defect",
        "audit-status current section must state that no current code-actionable P0/P1 defect remains.",
        errors,
    )

    for heading in (
        "### Local UI/research demo with dealing disabled",
        "### Supervised broker-connected demo",
        "### Live trading",
    ):
        require(
            readiness_current,
            re.escape(heading),
            f"readiness must include heading: {heading}",
            errors,
        )

    for phrase, description in (
        (r"IG_TRADING_ENABLED=false", "disabled dealing posture"),
        (r"fresh versioned database", "fresh-database-only supervised demo posture"),
        (r"supply-chain attestation/signing is \*\*not\*\* a supervised-demo blocker", "demo-vs-live supply-chain distinction"),
        (r"raw internal authority identifiers are acceptable", "current raw-identifier boundary statement"),
        (r"manual security posture", "manual security action statement"),
    ):
        require(readiness_current, phrase, f"readiness must include {description}.", errors)

    forbid(
        readiness_current.lower(),
        r"history cleanup completed|credential rotation completed",
        "readiness must not describe manual security actions as completed.",
        errors,
    )

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("PASS: audit/readiness current-status consistency checks succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
