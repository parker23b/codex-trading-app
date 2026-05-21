#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "scripts" / "repo_secrets_scan.toml"
TEXT_FILE_SUFFIXES = {
    "",
    ".env",
    ".example",
    ".ini",
    ".json",
    ".log",
    ".md",
    ".py",
    ".sh",
    ".text",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class Finding:
    scope: str
    kind: str
    path: str
    detail: str
    line_number: int | None = None

    def render(self) -> str:
        location = f"{self.path}:{self.line_number}" if self.line_number else self.path
        return f"[{self.scope}] {location} {self.kind}: {self.detail}"


@dataclass(frozen=True)
class ScanPolicy:
    max_scan_bytes: int
    ignored_path_prefixes: tuple[str, ...]
    allowed_path_patterns: tuple[re.Pattern[str], ...]
    forbidden_path_patterns: tuple[re.Pattern[str], ...]
    sensitive_env_keys: tuple[str, ...]
    placeholder_value_patterns: tuple[re.Pattern[str], ...]
    broker_payload_marker_keys: tuple[str, ...]

    @classmethod
    def load(cls, config_path: Path = DEFAULT_CONFIG_PATH) -> "ScanPolicy":
        with config_path.open("rb") as handle:
            raw = tomllib.load(handle)
        return cls(
            max_scan_bytes=int(raw["max_scan_bytes"]),
            ignored_path_prefixes=tuple(raw["ignored_path_prefixes"]),
            allowed_path_patterns=tuple(
                re.compile(pattern) for pattern in raw["allowed_path_patterns"]
            ),
            forbidden_path_patterns=tuple(
                re.compile(pattern) for pattern in raw["forbidden_path_patterns"]
            ),
            sensitive_env_keys=tuple(raw["sensitive_env_keys"]),
            placeholder_value_patterns=tuple(
                re.compile(pattern, re.IGNORECASE)
                for pattern in raw["placeholder_value_patterns"]
            ),
            broker_payload_marker_keys=tuple(raw["broker_payload_marker_keys"]),
        )


def _git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=check,
    )


def _normalize_path(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _is_allowed_path(path: str, policy: ScanPolicy) -> bool:
    return any(pattern.search(path) for pattern in policy.allowed_path_patterns)


def _is_ignored_path(path: str, policy: ScanPolicy) -> bool:
    return any(path.startswith(prefix) for prefix in policy.ignored_path_prefixes)


def _matches_forbidden_path(path: str, policy: ScanPolicy) -> bool:
    if _is_allowed_path(path, policy):
        return False
    return any(pattern.search(path) for pattern in policy.forbidden_path_patterns)


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            chunk = handle.read(4096)
    except OSError:
        return True
    return b"\x00" in chunk


def _should_scan_text(path: Path, policy: ScanPolicy) -> bool:
    if path.stat().st_size > policy.max_scan_bytes:
        return False
    if _is_binary(path):
        return False
    suffixes = path.suffixes
    if not suffixes:
        return path.name.startswith(".env")
    return any(suffix in TEXT_FILE_SUFFIXES for suffix in suffixes)


def _classify_path(path: str) -> set[str]:
    classes = {"text"}
    lower = path.lower()
    name = Path(path).name.lower()
    if name.startswith(".env") or "/.env" in lower:
        classes.add("env")
    if any(token in lower for token in ("dump", "payload", "response", "capture", "session")):
        classes.add("dump")
    if any(token in lower for token in ("/logs/", ".log", ".out", ".err")):
        classes.add("log")
    if any(token in lower for token in ("playwright-report", "test-results", ".har", ".trace")):
        classes.add("artifact")
    return classes


def _is_placeholder_value(value: str, policy: ScanPolicy) -> bool:
    normalized = value.strip().strip("\"'")
    if not normalized:
        return True
    return any(pattern.match(normalized) for pattern in policy.placeholder_value_patterns)


def _redact_assignment(key: str) -> str:
    return f"{key}=[REDACTED]"


def _redact_token_header(header: str) -> str:
    return f"{header}=[REDACTED]"


def _scan_env_assignments(
    path: str, text: str, policy: ScanPolicy, scope: str
) -> list[Finding]:
    if "env" not in _classify_path(path):
        return []
    findings: list[Finding] = []
    sensitive_keys = {key.upper() for key in policy.sensitive_env_keys}
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw_value = stripped.partition("=")
        normalized_key = key.strip().upper()
        if normalized_key not in sensitive_keys:
            continue
        value = raw_value.split("#", 1)[0].strip()
        if _is_placeholder_value(value, policy):
            continue
        findings.append(
            Finding(
                scope=scope,
                kind="sensitive-env-value",
                path=path,
                line_number=line_number,
                detail=_redact_assignment(normalized_key),
            )
        )
    return findings


def _scan_token_headers(
    path: str, text: str, classes: set[str], scope: str
) -> list[Finding]:
    if not ({"env", "dump", "log"} & classes):
        return []

    findings: list[Finding] = []
    patterns = (
        (
            "authorization-bearer",
            re.compile(r"(?i)\bAuthorization\b\s*[:=]\s*Bearer\s+([^\s,;|]+)"),
            "Authorization: Bearer [REDACTED]",
        ),
        (
            "session-token",
            re.compile(r"(?i)\b(CST|X-SECURITY-TOKEN|XST)\b\s*[:= -]\s*([^\s,;|]+)"),
            None,
        ),
        (
            "api-key-header",
            re.compile(r"(?i)\b(X-IG-API-KEY|X-API-KEY|API_KEY|OPENAI_API_KEY)\b\s*[:=]\s*([^\s,;|]+)"),
            None,
        ),
    )
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        for kind, pattern, fixed_detail in patterns:
            match = pattern.search(line)
            if not match:
                continue
            value = match.group(match.lastindex or 1)
            if re.fullmatch(r"\[REDACTED.*\]", value, re.IGNORECASE):
                continue
            if fixed_detail is not None:
                detail = fixed_detail
            else:
                detail = _redact_token_header(match.group(1).upper())
            findings.append(
                Finding(
                    scope=scope,
                    kind=kind,
                    path=path,
                    line_number=line_number,
                    detail=detail,
                )
            )
    return findings


def _scan_account_ids(
    path: str, text: str, classes: set[str], scope: str
) -> list[Finding]:
    if not ({"env", "dump", "log"} & classes):
        return []

    findings: list[Finding] = []
    pattern = re.compile(
        r"(?i)[\"']?(IG_ACCOUNT_ID|accountId|currentAccountId|account_id)[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9._:-]{6,})"
    )
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        match = pattern.search(line)
        if not match:
            continue
        findings.append(
            Finding(
                scope=scope,
                kind="account-identifier",
                path=path,
                line_number=line_number,
                detail=f"{match.group(1)}=[REDACTED]",
            )
        )
    return findings


def _scan_broker_payload_markers(
    path: str, text: str, classes: set[str], policy: ScanPolicy, scope: str
) -> list[Finding]:
    if "dump" not in classes and "log" not in classes:
        return []
    markers = [marker for marker in policy.broker_payload_marker_keys if marker in text]
    if len(markers) < 2:
        return []
    preview = ", ".join(sorted(markers[:4]))
    return [
        Finding(
            scope=scope,
            kind="broker-payload-markers",
            path=path,
            detail=f"broker payload markers detected ({preview})",
        )
    ]


def scan_working_tree(
    repo_root: Path,
    policy: ScanPolicy,
    *,
    paths: Sequence[str] | None = None,
    staged_only: bool = False,
) -> list[Finding]:
    findings: list[Finding] = []
    if paths is None:
        if staged_only:
            output = _git(
                repo_root, "diff", "--cached", "--name-only", "--diff-filter=ACMR"
            ).stdout
        else:
            output = _git(
                repo_root, "ls-files", "--cached", "--others", "--exclude-standard"
            ).stdout
        candidate_paths = [line.strip() for line in output.splitlines() if line.strip()]
    else:
        candidate_paths = [path for path in paths if path]

    for relative_path in candidate_paths:
        normalized = Path(relative_path).as_posix()
        if _is_ignored_path(normalized, policy):
            continue
        if _matches_forbidden_path(normalized, policy):
            findings.append(
                Finding(
                    scope="working-tree",
                    kind="forbidden-path",
                    path=normalized,
                    detail="tracked or pending file matches a sensitive local-only pattern",
                )
            )
        file_path = repo_root / normalized
        if not file_path.is_file():
            continue
        if not _should_scan_text(file_path, policy):
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        classes = _classify_path(normalized)
        findings.extend(_scan_env_assignments(normalized, text, policy, "working-tree"))
        findings.extend(_scan_token_headers(normalized, text, classes, "working-tree"))
        findings.extend(_scan_account_ids(normalized, text, classes, "working-tree"))
        findings.extend(
            _scan_broker_payload_markers(
                normalized, text, classes, policy, "working-tree"
            )
        )
    return findings


def scan_history(repo_root: Path, policy: ScanPolicy) -> list[Finding]:
    findings: list[Finding] = []
    history_paths_output = _git(
        repo_root, "log", "--all", "--name-only", "--pretty=format:"
    ).stdout
    seen_paths: set[str] = set()
    for line in history_paths_output.splitlines():
        path = line.strip()
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        if _matches_forbidden_path(path, policy):
            findings.append(
                Finding(
                    scope="history",
                    kind="historical-sensitive-path",
                    path=path,
                    detail="historically tracked path matches a sensitive local-only pattern",
                )
            )
    return findings


def _summarize(findings: Iterable[Finding]) -> str:
    items = list(findings)
    if not items:
        return "No findings."
    return "\n".join(finding.render() for finding in items)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan the repository for secrets-prone files, local credentials, and historical sensitive paths."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to the scan policy TOML file.",
    )
    parser.add_argument(
        "--mode",
        choices=("working-tree", "staged", "history", "all"),
        default="all",
        help="What to scan.",
    )
    parser.add_argument(
        "--allow-history-findings",
        action="store_true",
        help="Return success even when history findings exist.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional explicit paths to scan for working-tree or staged mode.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    config_path = Path(args.config)
    repo_root = config_path.resolve().parents[1]
    policy = ScanPolicy.load(config_path)

    findings: list[Finding] = []
    history_findings: list[Finding] = []

    if args.mode in {"working-tree", "all"}:
        findings.extend(
            scan_working_tree(repo_root, policy, paths=args.paths or None, staged_only=False)
        )
    if args.mode == "staged":
        findings.extend(
            scan_working_tree(repo_root, policy, paths=args.paths or None, staged_only=True)
        )
    if args.mode in {"history", "all"}:
        history_findings = scan_history(repo_root, policy)
        findings.extend(history_findings)

    print(_summarize(findings))

    if history_findings and args.allow_history_findings:
        return 0 if len(findings) == len(history_findings) else 1
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
