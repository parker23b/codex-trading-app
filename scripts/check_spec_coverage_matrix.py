#!/usr/bin/env python3
"""Validate spec coverage matrix completeness and evidence hygiene.

This check is intentionally conservative. It does not try to prove that the
named tests are sufficient; it only blocks obvious ways the matrix could
overstate confidence:

- missing P0/P1 spec IDs;
- unresolved P0/P1 rows with no next action;
- P0/P1 rows claiming High overall confidence without named behavioural
  evidence or explicit rationale;
- P0/P1 rows that appear to rely only on construction/config/process evidence.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = REPO_ROOT / "docs" / "spec"
MATRIX_PATH = SPEC_DIR / "99-spec-coverage-matrix.md"

SPEC_ID_RE = re.compile(r"^[A-Z][A-Z0-9-]+$")
SEVERITY_RE = re.compile(r"\bP[0-3]\b")
GROUPED_IDS_RE = re.compile(r"Grouped coverage IDs:\s*(.+)")
ID_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9-]+\b")
CONFIDENCE_FLAG_RE = re.compile(r"(Low|Unknown|Needs audit|Needs test|Needs confirmation)")
BEHAVIOURAL_VERIFICATION_LEVELS = {
    "SERVICE_VERIFIED",
    "ROUTE_VERIFIED",
    "FRONTEND_VERIFIED",
    "FULL_STACK_VERIFIED",
    "E2E_VERIFIED",
}
BEHAVIOURAL_EVIDENCE_RE = re.compile(
    r"("
    r"test_[A-Za-z0-9_]+"
    r"|[A-Za-z0-9_./-]+\.test\.[A-Za-z0-9]+"
    r"|[A-Za-z0-9_./-]+\.spec\.[A-Za-z0-9]+"
    r"|AUDIT-[A-Z0-9-]+[^|]*regression"
    r")"
)
EXPLICIT_RATIONALE_RE = re.compile(r"explicit rationale", re.IGNORECASE)
CONSTRUCTION_ONLY_MARKERS = (
    "typecheck",
    "lint",
    "format",
    "config review",
    "code review",
    "review guidance",
    "route inventory",
    "code search",
    "process rule",
    "frontend code gate exists",
    "all app pages exist",
)


@dataclass(frozen=True)
class SpecEntry:
    spec_id: str
    severity: str
    source_file: str


@dataclass(frozen=True)
class MatrixRow:
    spec_id: str
    severity: str
    behaviour: str
    backend_evidence: str
    route_evidence: str
    frontend_evidence: str
    current_verification: str
    target_verification: str
    backend_confidence: str
    route_confidence: str
    frontend_confidence: str
    overall_confidence: str
    next_action: str
    notes: str
    line_number: int

    @property
    def evidence_blob(self) -> str:
        return " | ".join(
            [
                self.backend_evidence,
                self.route_evidence,
                self.frontend_evidence,
                self.notes,
            ]
        )

    @property
    def confidence_blob(self) -> str:
        return " | ".join(
            [
                self.backend_confidence,
                self.route_confidence,
                self.frontend_confidence,
                self.overall_confidence,
            ]
        )


def parse_spec_entries() -> dict[str, SpecEntry]:
    entries: dict[str, SpecEntry] = {}
    for path in sorted(SPEC_DIR.glob("*.md")):
        if path.name == MATRIX_PATH.name:
            continue
        for line in path.read_text().splitlines():
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not cells:
                continue
            first = cells[0]
            if first in {"Spec ID", "Boundary ID", "Flow ID", "ID", "---"}:
                continue
            if set(first) == {"-"} or not SPEC_ID_RE.match(first):
                continue
            severity = None
            for cell in reversed(cells):
                if cell in {"P0", "P1", "P2", "P3"}:
                    severity = cell
                    break
            if severity is None:
                continue
            if severity not in {"P0", "P1"}:
                continue
            entries[first] = SpecEntry(spec_id=first, severity=severity, source_file=path.name)
    return entries


def parse_matrix_rows() -> dict[str, MatrixRow]:
    rows: dict[str, MatrixRow] = {}
    lines = MATRIX_PATH.read_text().splitlines()
    for index, line in enumerate(lines, start=1):
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 16:
            continue
        first = cells[0]
        if first in {"Spec ID", "---"} or set(first) == {"-"} or not SPEC_ID_RE.match(first):
            continue
        rows[first] = MatrixRow(
            spec_id=first,
            severity=cells[1],
            behaviour=cells[2],
            backend_evidence=cells[4],
            route_evidence=cells[5],
            frontend_evidence=cells[6],
            current_verification=cells[8],
            target_verification=cells[9],
            backend_confidence=cells[10],
            route_confidence=cells[11],
            frontend_confidence=cells[12],
            overall_confidence=cells[13],
            next_action=cells[14],
            notes=cells[15],
            line_number=index,
        )
    return rows


def parse_grouped_ids() -> set[str]:
    grouped_ids: set[str] = set()
    for line in MATRIX_PATH.read_text().splitlines():
        match = GROUPED_IDS_RE.search(line)
        if not match:
            continue
        for token in ID_TOKEN_RE.findall(match.group(1)):
            grouped_ids.add(token)
    return grouped_ids


def has_named_behavioural_evidence(text: str) -> bool:
    return bool(BEHAVIOURAL_EVIDENCE_RE.search(text))


def has_only_construction_markers(text: str) -> bool:
    lowered = text.lower()
    if has_named_behavioural_evidence(text):
        return False
    return any(marker in lowered for marker in CONSTRUCTION_ONLY_MARKERS)


def validate(spec_entries: dict[str, SpecEntry], matrix_rows: dict[str, MatrixRow], grouped_ids: set[str]) -> list[str]:
    errors: list[str] = []

    covered_ids = set(matrix_rows) | grouped_ids
    missing_ids = sorted(spec_id for spec_id in spec_entries if spec_id not in covered_ids)
    if missing_ids:
        errors.append(
            "Missing P0/P1 spec IDs in matrix/grouped coverage: "
            + ", ".join(missing_ids)
        )

    for row in matrix_rows.values():
        if row.severity not in {"P0", "P1"}:
            continue

        if CONFIDENCE_FLAG_RE.search(row.confidence_blob) and not row.next_action.strip():
            errors.append(
                f"{row.spec_id} (line {row.line_number}) has unresolved confidence but no next action."
            )

        if row.overall_confidence.strip() == "High":
            if not has_named_behavioural_evidence(row.evidence_blob) and not EXPLICIT_RATIONALE_RE.search(
                row.notes
            ):
                errors.append(
                    f"{row.spec_id} (line {row.line_number}) claims High overall confidence without named behavioural evidence or explicit rationale."
                )

        if row.current_verification.strip("`") in BEHAVIOURAL_VERIFICATION_LEVELS:
            if has_only_construction_markers(
                " | ".join([row.backend_evidence, row.route_evidence, row.frontend_evidence])
            ):
                errors.append(
                    f"{row.spec_id} (line {row.line_number}) appears to rely on construction/config/process evidence without behavioural proof."
                )

    return errors


def build_unresolved_index(matrix_rows: dict[str, MatrixRow]) -> dict[str, list[str]]:
    buckets = {
        "Needs audit": [],
        "Needs confirmation": [],
        "Needs test": [],
        "Unknown": [],
    }
    for row in matrix_rows.values():
        if row.severity not in {"P0", "P1"}:
            continue
        for label in buckets:
            if label in row.confidence_blob:
                buckets[label].append(row.spec_id)
    for label in buckets:
        buckets[label] = sorted(set(buckets[label]))
    return buckets


def print_report(
    spec_entries: dict[str, SpecEntry],
    matrix_rows: dict[str, MatrixRow],
    grouped_ids: set[str],
    errors: list[str],
) -> None:
    covered_ids = set(matrix_rows) | grouped_ids
    unresolved = build_unresolved_index(matrix_rows)
    severity_counts = Counter(entry.severity for entry in spec_entries.values())
    print("Spec coverage matrix check")
    print(f"- P0/P1 spec IDs found: {len(spec_entries)} ({dict(severity_counts)})")
    print(f"- Explicit matrix rows: {len(matrix_rows)}")
    print(f"- Grouped coverage IDs: {len(grouped_ids)}")
    print(f"- Covered P0/P1 IDs: {len(covered_ids & set(spec_entries))}")
    print("- Unresolved evidence index:")
    for label, ids in unresolved.items():
        suffix = ", ".join(ids) if ids else "none"
        print(f"  - {label}: {len(ids)} -> {suffix}")
    if errors:
        print("- Result: FAIL")
        for error in errors:
            print(f"  - {error}")
    else:
        print("- Result: PASS")


def main() -> int:
    spec_entries = parse_spec_entries()
    matrix_rows = parse_matrix_rows()
    grouped_ids = parse_grouped_ids()
    errors = validate(spec_entries, matrix_rows, grouped_ids)
    print_report(spec_entries, matrix_rows, grouped_ids, errors)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
