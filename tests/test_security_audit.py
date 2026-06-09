"""Theme 11 — security & data-policy audits (T11-88/90/91)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_PKG_DIRS = ["pipeline", "fr24", "integration", "scripts", "server",
             "readiness", "federation", "llm", "earthgpt"]


def _py_files():
    for d in _PKG_DIRS:
        base = REPO / d
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            yield p
    for name in ("run_all.py", "release_check.py", "run_modes.py", "provenance_utils.py"):
        p = REPO / name
        if p.exists():
            yield p


# ── T11-91 SQL parameterization audit ────────────────────────────────────────

# Classic injection vectors: %-formatted or .format()-built SQL handed to
# execute/executemany. (f-strings interpolating *literal* column lists are
# reviewed and allowed; %/.format dynamic SQL is not.)
_PCT_SQL = re.compile(r"\.executemany?\(\s*[\"'][^\"']*[\"']\s*%")
_FMT_SQL = re.compile(r"\.executemany?\(\s*[\"'][^\"']*[\"']\s*\.format\(")


def test_no_percent_or_format_sql():
    offenders = []
    for p in _py_files():
        text = p.read_text(encoding="utf-8", errors="ignore")
        if _PCT_SQL.search(text) or _FMT_SQL.search(text):
            offenders.append(str(p.relative_to(REPO)))
    assert not offenders, f"%/.format()-built SQL found (use ? params): {offenders}"


# ── T11-88 secrets scan ──────────────────────────────────────────────────────

_SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "aws_secret": re.compile(r"aws_secret_access_key\s*=\s*[\"'][A-Za-z0-9/+=]{40}[\"']"),
}


def test_no_committed_secrets():
    offenders = []
    scan_dirs = _PKG_DIRS + ["configs", "docs"]
    files = []
    for d in scan_dirs:
        base = REPO / d
        if base.is_dir():
            files += [p for p in base.rglob("*")
                      if p.is_file() and p.suffix in (".py", ".yaml", ".yml", ".md", ".json", ".txt")]
    for p in files:
        text = p.read_text(encoding="utf-8", errors="ignore")
        for name, pat in _SECRET_PATTERNS.items():
            if pat.search(text):
                offenders.append(f"{p.relative_to(REPO)}:{name}")
    assert not offenders, f"possible committed secrets: {offenders}"


def test_env_example_exists_and_has_no_values():
    example = REPO / ".env.example"
    assert example.exists(), ".env.example is missing"
    for line in example.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, val = line.partition("=")
        # Only a default user-agent string is allowed to carry a value.
        if key.strip() == "PRAW_USER_AGENT":
            continue
        assert val.strip() == "", f".env.example must not ship a value for {key}"


# ── T11-90 path-traversal safety ─────────────────────────────────────────────

def test_safe_join_allows_within(tmp_path):
    from pipeline.path_safety import safe_join

    result = safe_join(tmp_path, "sub", "file.png")
    assert str(result).startswith(str(tmp_path.resolve()))


def test_safe_join_blocks_dotdot(tmp_path):
    from pipeline.path_safety import PathTraversalError, safe_join

    with pytest.raises(PathTraversalError):
        safe_join(tmp_path, "..", "etc", "passwd")


def test_safe_join_blocks_absolute(tmp_path):
    from pipeline.path_safety import PathTraversalError, safe_join

    with pytest.raises(PathTraversalError):
        safe_join(tmp_path, "/etc/passwd")


def test_is_within(tmp_path):
    from pipeline.path_safety import is_within

    assert is_within(tmp_path, tmp_path / "a")
    assert is_within(tmp_path, tmp_path)
    assert not is_within(tmp_path / "base", tmp_path / "other" / "x")
