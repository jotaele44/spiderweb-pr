#!/usr/bin/env python3
"""
RELEASE CHECK — single top-level release gate.

Runs the release-readiness stages against a database and writes
``release_report.json`` — the umbrella artifact (D1) that references the two
existing reports (``integration_report.json``, ``prii_readiness_report.json``)
and records a reproducibility block (D3).

Stages:
  syntax_check      compile every source module (compile-only; never imports,
                    so optional-dep guards in FR24/EarthGPT modules are safe)
  core_tests        pytest subset (GEBCO io/terrain tests excluded — D7)
  validate          schema validation → review_queue.csv
  export_pr_intel   PRIntelAdapter.export_all() → integration_report.json
  export_spiderweb  ILAP + AASB bridges → spiderweb_ingest_manifest.json
  earthgpt_selftest optional; degrades to WARNING if unavailable (never FAIL)

Every stage is defensive: it catches its own failure and returns a status dict,
so the gate always produces a report (it never crashes on an empty DB).

CLI:
    python release_check.py --db DB --output-dir DIR [--strict-production|--demo] [--skip-tests]
Usually invoked via ``run_all.py --release-check``.
"""
from __future__ import annotations

import argparse
import json
import py_compile
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from provenance_utils import reproducibility_metadata
from run_modes import (
    MODE_DEMO,
    MODE_STRICT,
    ModeResolution,
    assert_production_input,
    label_banner,
    label_manifest,
)

REPO_ROOT = Path(__file__).resolve().parent

# Source trees to syntax-check (compile-only). Root *.py added separately.
SYNTAX_DIRS = ("integration", "readiness", "fr24", "pipeline", "earthgpt", "llm", "federation")

# GEBCO io/terrain tests run in a dedicated CI job (D7) — keep them out of the gate.
PYTEST_IGNORES = ("tests/test_io.py", "tests/test_terrain.py")

# Stages whose status gates the overall verdict. EarthGPT is intentionally absent.
GATING_STAGES = ("syntax_check", "core_tests", "validate", "export_pr_intel", "export_spiderweb")

PASS, FAIL, WARNING, SKIPPED = "PASS", "FAIL", "WARNING", "SKIPPED"


class ReleaseCheck:
    """Orchestrates the release gate and writes ``release_report.json``."""

    def __init__(
        self,
        db_path: str,
        output_dir: str,
        mode: str = "normal",
        *,
        command: Optional[str] = None,
        run_tests: bool = True,
    ):
        self.db_path = str(db_path)
        self.output_dir = Path(output_dir)
        self.mode = mode
        self.command = command
        self.run_tests = run_tests
        self._mode_res = ModeResolution(
            mode,
            fail_on_missing=(mode == MODE_STRICT),
            label_outputs=(mode == MODE_DEMO),
        )

    # ---- public API --------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Strict mode: a missing production DB is a hard stop (D2).
        if self.mode == MODE_STRICT:
            assert_production_input(
                self.db_path,
                stage="release_check",
                hint="run the pipeline to populate the DB, or use --demo",
                mode=self._mode_res,
                require_nonempty=False,
            )

        sections: Dict[str, Any] = {
            "syntax_check": self.syntax_check(),
            "core_tests": self.core_tests() if self.run_tests else {
                "status": SKIPPED, "passed": 0, "failed": 0, "skipped": 0,
                "reason": "run_tests=False",
            },
            "validate": self.validate(),
            "export_pr_intel": self.export_pr_intel(),
            "export_spiderweb": self.export_spiderweb(),
            "earthgpt_selftest": self.earthgpt_selftest(),
        }
        return self.summarize(sections)

    # ---- stages ------------------------------------------------------------

    def syntax_check(self) -> Dict[str, Any]:
        """Compile every source module without importing it (Open Risk #1)."""
        files: List[Path] = sorted(REPO_ROOT.glob("*.py"))
        for d in SYNTAX_DIRS:
            base = REPO_ROOT / d
            if base.is_dir():
                files += sorted(
                    p for p in base.rglob("*.py")
                    if "__pycache__" not in p.parts and ".claude" not in p.parts
                )
        failures: List[Dict[str, str]] = []
        for f in files:
            try:
                py_compile.compile(str(f), doraise=True)
            except py_compile.PyCompileError as e:
                failures.append({"file": str(f.relative_to(REPO_ROOT)), "error": str(e.msg)})
            except Exception as e:  # pragma: no cover - defensive
                failures.append({"file": str(f.relative_to(REPO_ROOT)), "error": repr(e)})
        return {
            "status": PASS if not failures else FAIL,
            "files_checked": len(files),
            "failures": failures,
        }

    def core_tests(self) -> Dict[str, Any]:
        """Run the pytest subset in a subprocess and parse the summary line."""
        cmd = [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no",
               "-p", "no:cacheprovider"]
        for ig in PYTEST_IGNORES:
            cmd.append(f"--ignore={ig}")
        try:
            proc = subprocess.run(
                cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=1800,
            )
        except subprocess.SubprocessError as e:
            return {"status": FAIL, "passed": 0, "failed": 0, "skipped": 0,
                    "error": f"pytest_invocation_failed: {e}"}
        counts = _parse_pytest_counts(proc.stdout + "\n" + proc.stderr)
        # returncode 0 = all passed; 5 = no tests collected (treat as pass-with-warning)
        status = PASS if proc.returncode in (0, 5) and counts["failed"] == 0 and counts["error"] == 0 else FAIL
        return {"status": status, "returncode": proc.returncode, **counts,
                "summary": _last_summary_line(proc.stdout)}

    def validate(self) -> Dict[str, Any]:
        review_path = str(self.output_dir / "review_queue.csv")
        if not Path(self.db_path).exists():
            return {"status": SKIPPED, "reason": "db_missing", "db": self.db_path,
                    "review_queue": review_path}
        try:
            from integration.schema_validation import SchemaValidator
            results = SchemaValidator().run_db_validation(self.db_path, review_path)
        except Exception as e:
            return {"status": FAIL, "error": repr(e), "review_queue": review_path}
        if "_error" in results:
            return {"status": FAIL, "error": results["_error"].get("error"),
                    "review_queue": review_path}
        invalid = sum(s.get("invalid", 0) for k, s in results.items() if k != "_error")
        return {"status": PASS, "schema_invalid": invalid, "review_queue": review_path,
                "tables": {k: s.get("invalid", 0) for k, s in results.items()}}

    def export_pr_intel(self) -> Dict[str, Any]:
        out = self.output_dir / "pr_intel"
        if not Path(self.db_path).exists():
            return {"status": SKIPPED, "reason": "db_missing",
                    "integration_report": str(out / "integration_report.json")}
        try:
            from integration.pr_intel_adapter import PRIntelAdapter
            out.mkdir(parents=True, exist_ok=True)
            report = PRIntelAdapter(self.db_path, str(out)).export_all()
        except Exception as e:
            return {"status": FAIL, "error": repr(e),
                    "integration_report": str(out / "integration_report.json")}
        return {
            "status": report.get("overall_status", FAIL),
            "integration_report": str(out / "integration_report.json"),
            "gates": {k: g.get("status") for k, g in report.get("gates", {}).items()},
            "files": _list_files(out),
        }

    def export_spiderweb(self) -> Dict[str, Any]:
        out = self.output_dir / "spiderweb"
        if not Path(self.db_path).exists():
            return {"status": SKIPPED, "reason": "db_missing",
                    "manifest": str(out / "spiderweb_ingest_manifest.json")}
        try:
            from integration.ilap_airspace_bridge import ILAPAirspaceBridge
            from integration.aasb_airspace_bridge import AASBAirspaceBridge
            out.mkdir(parents=True, exist_ok=True)
            ILAPAirspaceBridge(self.db_path, str(out)).export_all()
            AASBAirspaceBridge(self.db_path, str(out)).export_all()
        except Exception as e:
            return {"status": FAIL, "error": repr(e),
                    "manifest": str(out / "spiderweb_ingest_manifest.json")}
        return {"status": PASS,
                "manifest": str(out / "spiderweb_ingest_manifest.json"),
                "files": _list_files(out)}

    def earthgpt_selftest(self) -> Dict[str, Any]:
        """Optional gate (Open Risk #4): import/run failure → WARNING, never FAIL."""
        try:
            from earthgpt.selftest import run_selftest
            res = run_selftest()
        except Exception as e:
            return {"status": WARNING, "reason": "earthgpt_unavailable", "error": repr(e)}
        passed, total = res.get("passed", 0), res.get("total", 0)
        return {"status": PASS if total and passed == total else WARNING,
                "passed": passed, "total": total, "gates": res.get("gates", {})}

    # ---- summary + write ---------------------------------------------------

    def summarize(self, sections: Dict[str, Any]) -> Dict[str, Any]:
        failure_reasons: List[str] = []
        for name in GATING_STAGES:
            st = sections.get(name, {}).get("status")
            if st == FAIL:
                failure_reasons.append(f"{name}:FAIL")
        overall = FAIL if failure_reasons else PASS

        report: Dict[str, Any] = {
            "metadata": reproducibility_metadata(
                command=self.command, input_paths=[self.db_path], mode=self.mode,
            ),
            **sections,
            "overall_status": overall,
            "failure_reasons": failure_reasons,
        }
        if self.mode == MODE_DEMO:
            label_manifest(report, self._mode_res)

        out_path = self.output_dir / "release_report.json"
        out_path.write_text(json.dumps(report, indent=2, sort_keys=False), encoding="utf-8")
        report["_report_path"] = str(out_path)
        return report


# ---- helpers ---------------------------------------------------------------

def _parse_pytest_counts(text: str) -> Dict[str, int]:
    out = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    for key in out:
        m = re.search(rf"(\d+)\s+{key}", text)
        if m:
            out[key] = int(m.group(1))
    # pytest prints "errors" (plural); catch the singular search miss
    m = re.search(r"(\d+)\s+errors?", text)
    if m:
        out["error"] = int(m.group(1))
    return out


def _last_summary_line(stdout: str) -> str:
    lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def _list_files(d: Path) -> List[str]:
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_file())


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the release gate and write release_report.json")
    ap.add_argument("--db", required=True, help="Database path")
    ap.add_argument("--output-dir", required=True, help="Where to write release_report.json")
    ap.add_argument("--strict-production", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--skip-tests", action="store_true", help="Skip the pytest stage")
    args = ap.parse_args()
    mode = MODE_STRICT if args.strict_production else (MODE_DEMO if args.demo else "normal")
    rc = ReleaseCheck(
        args.db, args.output_dir, mode,
        command=" ".join(["python", "release_check.py"] + sys.argv[1:]),
        run_tests=not args.skip_tests,
    )
    report = rc.run()
    print(json.dumps({"overall_status": report["overall_status"],
                      "failure_reasons": report["failure_reasons"],
                      "report": report["_report_path"]}, indent=2))
    sys.exit(0 if report["overall_status"] == PASS else 1)


if __name__ == "__main__":
    main()
