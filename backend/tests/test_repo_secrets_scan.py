from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "repo_secrets_scan.py"
CONFIG_PATH = REPO_ROOT / "scripts" / "repo_secrets_scan.toml"


def _load_scan_module():
    spec = importlib.util.spec_from_file_location("repo_secrets_scan", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_policy_loads_expected_sensitive_keys():
    scan = _load_scan_module()

    policy = scan.ScanPolicy.load(CONFIG_PATH)

    assert "IG_PASSWORD" in policy.sensitive_env_keys
    assert "OPERATOR_API_TOKEN" in policy.sensitive_env_keys
    assert "OPERATOR_API_CREDENTIALS" in policy.sensitive_env_keys
    assert policy.max_scan_bytes >= 100_000


def test_scan_working_tree_flags_real_env_secret_without_echoing_raw_value(
    tmp_path: Path,
):
    scan = _load_scan_module()
    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    env_path = repo_root / "backend" / ".env"
    env_path.parent.mkdir(parents=True)
    env_path.write_text("IG_PASSWORD=real-super-secret\n", encoding="utf-8")
    policy = scan.ScanPolicy.load(CONFIG_PATH)

    findings = scan.scan_working_tree(repo_root, policy, paths=["backend/.env"])

    assert any(finding.kind == "forbidden-path" for finding in findings)
    rendered = "\n".join(finding.render() for finding in findings)
    assert "IG_PASSWORD=[REDACTED]" in rendered
    assert "real-super-secret" not in rendered


def test_scan_working_tree_allows_safe_env_examples(tmp_path: Path):
    scan = _load_scan_module()
    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    example_path = repo_root / "backend" / ".env.example"
    example_path.parent.mkdir(parents=True)
    example_path.write_text("IG_PASSWORD=\n# OPENAI_API_KEY=...\n", encoding="utf-8")
    policy = scan.ScanPolicy.load(CONFIG_PATH)

    findings = scan.scan_working_tree(repo_root, policy, paths=["backend/.env.example"])

    assert findings == []


def test_scan_working_tree_flags_broker_dump_markers(tmp_path: Path):
    scan = _load_scan_module()
    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    payload_path = repo_root / "captures" / "ig-response.json"
    payload_path.parent.mkdir(parents=True)
    payload_path.write_text(
        '{"accountId":"ACC-12345","dealReference":"DEAL-99999","positions":[]}',
        encoding="utf-8",
    )
    policy = scan.ScanPolicy.load(CONFIG_PATH)

    findings = scan.scan_working_tree(
        repo_root, policy, paths=["captures/ig-response.json"]
    )

    kinds = {finding.kind for finding in findings}
    assert "forbidden-path" in kinds
    assert "account-identifier" in kinds
    assert "broker-payload-markers" in kinds


def test_scan_history_reports_historical_sensitive_paths(tmp_path: Path):
    scan = _load_scan_module()
    repo_root = tmp_path
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    db_path = repo_root / "backend" / "trading_platform.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"sqlite data")
    subprocess.run(
        ["git", "add", "backend/trading_platform.db"], cwd=repo_root, check=True
    )
    subprocess.run(
        ["git", "commit", "-m", "add db"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    db_path.unlink()
    subprocess.run(["git", "add", "-u"], cwd=repo_root, check=True)
    subprocess.run(
        ["git", "commit", "-m", "remove db"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    policy = scan.ScanPolicy.load(CONFIG_PATH)

    findings = scan.scan_history(repo_root, policy)

    assert any(
        finding.path == "backend/trading_platform.db"
        and finding.kind == "historical-sensitive-path"
        for finding in findings
    )


def test_cli_allows_history_findings_when_requested(tmp_path: Path):
    repo_root = tmp_path
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "repo_secrets_scan.py").write_text(
        SCRIPT_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (scripts_dir / "repo_secrets_scan.toml").write_text(
        CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    db_path = repo_root / "trading_platform.db"
    db_path.write_bytes(b"sqlite data")
    subprocess.run(["git", "add", "trading_platform.db"], cwd=repo_root, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add db"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    db_path.unlink()
    subprocess.run(["git", "add", "-u"], cwd=repo_root, check=True)
    subprocess.run(
        ["git", "commit", "-m", "remove db"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )

    result = subprocess.run(
        [
            "python3",
            "scripts/repo_secrets_scan.py",
            "--config",
            "scripts/repo_secrets_scan.toml",
            "--mode",
            "history",
            "--allow-history-findings",
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "trading_platform.db" in result.stdout
