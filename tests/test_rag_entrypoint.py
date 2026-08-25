from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_backend_rag_entrypoint_resolves_and_exposes_cli_help() -> None:
    """The FastAPI backend invokes ROOT/query_llm.py; prove that path is live.

    ``--help`` exits before model/index loading, so this is a deterministic
    regression gate for the exact path failure without downloading LLM assets.
    """
    proc = subprocess.run(
        [sys.executable, str(ROOT / "query_llm.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Query your PRUAP data with a local LLM" in proc.stdout
