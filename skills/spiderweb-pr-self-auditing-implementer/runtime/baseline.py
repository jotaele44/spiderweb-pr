from __future__ import annotations
from pathlib import Path
import re

def parse_ci_contract(ci_text: str) -> dict:
    commands = []
    for line in ci_text.splitlines():
        s = line.strip()
        if s.startswith(("python ", "python3 ", "pip install", "test -f", "find .")):
            commands.append(s)
    floor = None
    m = re.search(r"--cov-fail-under=(\d+(?:\.\d+)?)", ci_text)
    if m:
        floor = float(m.group(1))
    return {"commands": commands, "coverage_floor": floor}

def baseline(repo: Path) -> dict:
    ci = repo / ".github/workflows/ci.yml"
    pyproject = repo / "pyproject.toml"
    return {"ci_present": ci.exists(), "pyproject_present": pyproject.exists(), "ci_contract": parse_ci_contract(ci.read_text()) if ci.exists() else {}, "ready": ci.exists() and pyproject.exists()}
