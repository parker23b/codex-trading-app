#!/usr/bin/env python3
"""Guard the current audit/readiness risk register against stale drift.

This check is intentionally explicit and conservative. It validates only the
small set of current-status claims that are easy to drift back into
contradiction:

- historical verification stays anchored to the latest reviewed successful
  Repo Audit run without being confused for current readiness;
- current P0 remediation and open P1 findings remain visible in the audit and coverage matrix;
- broker-connected dealing remains gated while production-dialect P0 evidence is pending;
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
        (matrix_current, "coverage-matrix current section"),
    ):
        require(
            text,
            re.escape(LATEST_SUCCESS_RUN_ID),
            f"{label} must reference the latest reviewed successful Repo Audit run {LATEST_SUCCESS_RUN_ID}.",
            errors,
        )

    for text, label in (
        (audit_current, "audit-status current section"),
        (readiness_current, "readiness current section"),
        (matrix_current, "coverage-matrix current section"),
    ):
        for run_id in OLDER_RUN_IDS:
            forbid(
                text,
                re.escape(run_id),
                f"{label} must not present older run {run_id} as current truth.",
                errors,
            )

    remediated_p0_findings = {
        "AUDIT-ARCH-001": r"Verified",
        "AUDIT-RISK-004": r"Fixed;\s*Postgres verification pending",
        "AUDIT-RUNTIME-002": r"Fixed;\s*Postgres verification pending",
    }
    for finding_id, status in remediated_p0_findings.items():
        require(
            audit_current,
            rf"\|\s*`{re.escape(finding_id)}`\s*\|\s*P0\s*\|\s*{status}\s*\|",
            f"audit-status current risk register must preserve the current remediation status for {finding_id}.",
            errors,
        )
        require(
            matrix_current,
            re.escape(finding_id),
            f"coverage-matrix current section must reference {finding_id}.",
            errors,
        )

    verified_p1_findings = {
        "AUDIT-ARCH-002": "P1",
        "AUDIT-SEC-004": "P1",
        "AUDIT-BROKER-006": "P1",
    }
    for finding_id, severity in verified_p1_findings.items():
        require(
            audit_current,
            rf"\|\s*`{re.escape(finding_id)}`\s*\|\s*{severity}\s*\|\s*Verified\s*\|",
            f"audit-status current risk register must classify {finding_id} as verified {severity}.",
            errors,
        )
        require(
            matrix_current,
            re.escape(finding_id),
            f"coverage-matrix current section must reference {finding_id}.",
            errors,
        )

    expected_open_findings = {"AUDIT-ARCH-003": "P1"}
    for finding_id, severity in expected_open_findings.items():
        require(
            audit_current,
            rf"\|\s*`{re.escape(finding_id)}`\s*\|\s*{severity}\s*\|\s*Open\s*\|",
            f"audit-status current risk register must classify {finding_id} as open {severity}.",
            errors,
        )
        require(
            matrix_current,
            re.escape(finding_id),
            f"coverage-matrix current section must reference {finding_id}.",
            errors,
        )

    require(
        audit_current,
        r"\|\s*`AUDIT-DOC-006`\s*\|\s*P1\s*\|\s*Verified\s*\|",
        "audit-status current risk register must keep AUDIT-DOC-006 verified.",
        errors,
    )
    require(
        matrix_current,
        r"AUDIT-DOC-006",
        "coverage-matrix current section must reference AUDIT-DOC-006.",
        errors,
    )

    require(
        audit_current.lower(),
        r"pending refreshed evidence for broker-connected demo dealing",
        "audit-status current section must keep broker-connected demo dealing behind the evidence gate.",
        errors,
    )
    require(
        audit_current,
        r"three code-actionable P0 gaps.*are fixed",
        "audit-status current section must state that the three code-actionable P0 gaps are fixed.",
        errors,
    )

    for heading in (
        "### Local UI, research, and read-only smoke testing",
        "### Broker-connected demo dealing",
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
        (r"committed Postgres cross-connection tests pass in CI", "Postgres P0 evidence gate"),
        (r"not yet approved for broker-connected demo dealing", "pending demo-dealing posture"),
        (r"not approve unattended autonomy", "blocked unattended-autonomy posture"),
    ):
        require(readiness_current, phrase, f"readiness must include {description}.", errors)

    require(
        matrix_text,
        r"\|\s*RISK-014\s*\|[^\n]*`SERVICE_VERIFIED`; Postgres rehearsal pending CI",
        "coverage matrix must keep RISK-014 linked to the pending Postgres verification gate.",
        errors,
    )
    require(
        matrix_current,
        r"2026-06-01 historical closure snapshot",
        "coverage matrix must label the previous closure snapshot as historical.",
        errors,
    )

    for text, label in (
        (audit_current.lower(), "audit-status current section"),
        (readiness_current.lower(), "readiness current section"),
    ):
        forbid(
            text,
            r"ready for a human-supervised ig demo|ready for supervised broker-connected demo",
            f"{label} must not claim dealing readiness before the Postgres and preflight gates pass.",
            errors,
        )
        forbid(
            text,
            r"no current code-actionable p0 or p1 defect",
            f"{label} must not claim that no actionable P0/P1 remains.",
            errors,
        )

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
