from __future__ import annotations

import json
from pathlib import Path

from scripts.check_gui_parity import main


def test_gui_parity_checker_passes_repository_surface(tmp_path: Path):
    report = tmp_path / "report.json"
    assert main(["--report", str(report)]) == 0
    payload = json.loads(report.read_text())
    assert payload["passed"] is True
    assert payload["summary"]["new_gaps"] == 0
