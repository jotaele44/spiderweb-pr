from __future__ import annotations
import subprocess
from pathlib import Path

def run(commands: list[list[str]], cwd: Path) -> dict:
    results = []
    for cmd in commands:
        p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
        results.append({"command": cmd, "returncode": p.returncode, "stdout": p.stdout[-4000:], "stderr": p.stderr[-4000:]})
        if p.returncode != 0:
            break
    return {"passed": all(r["returncode"] == 0 for r in results), "results": results}
