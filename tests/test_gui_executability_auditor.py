from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_gui_executability.py"
SPEC = importlib.util.spec_from_file_location("audit_gui_executability", SCRIPT)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


def write_source(tmp_path: Path, content: str) -> Path:
    root = tmp_path
    source = root / "server" / "frontend" / "src" / "Fixture.tsx"
    source.parent.mkdir(parents=True)
    source.write_text(content, encoding="utf-8")
    return root


def test_wired_symbol_is_not_upgraded_to_executable(tmp_path: Path) -> None:
    root = write_source(
        tmp_path,
        """
        const run = () => { return 1; };
        export function Fixture() { return <button onClick={run}>Run</button>; }
        """,
    )
    ledger = MOD.build_ledger(root)
    assert ledger["coverage"]["discovered_manifestations"] == 1
    item = ledger["capabilities"][0]
    assert item["final_state"] == "WIRED"
    assert "downstream executability is not proven" in item["limitations"][0]
    assert ledger["certification"] == "AUDIT_ONLY"


def test_clear_todo_handler_is_stub(tmp_path: Path) -> None:
    root = write_source(
        tmp_path,
        """
        const exportData = () => { console.warn('TODO export'); };
        export function Fixture() { return <button onClick={exportData}>Export</button>; }
        """,
    )
    ledger = MOD.build_ledger(root)
    item = ledger["capabilities"][0]
    assert item["final_state"] == "STUB"
    assert item["gap_codes"] == ("STUB_IMPLEMENTATION",)


def test_missing_handler_is_dead_surface_only_for_plain_button(tmp_path: Path) -> None:
    root = write_source(
        tmp_path,
        "export function Fixture() { return <button>Decorative action</button>; }",
    )
    item = MOD.build_ledger(root)["capabilities"][0]
    assert item["final_state"] == "DEAD_SURFACE"
    assert item["gap_codes"] == ("GUI_HANDLER_MISSING",)


def test_submit_without_local_onclick_fails_closed(tmp_path: Path) -> None:
    root = write_source(
        tmp_path,
        "export function Fixture() { return <button type=\"submit\">Search</button>; }",
    )
    item = MOD.build_ledger(root)["capabilities"][0]
    assert item["final_state"] == "UNRESOLVED"
    assert item["gap_codes"] == ("FORM_BINDING_UNRESOLVED",)


def test_inline_dynamic_handler_is_wired_but_identity_unresolved(tmp_path: Path) -> None:
    root = write_source(
        tmp_path,
        "export function Fixture() { return <button onClick={() => choose('x')}>Pick</button>; }",
    )
    item = MOD.build_ledger(root)["capabilities"][0]
    assert item["final_state"] == "WIRED"
    assert item["handler_symbol"] is None


def test_arithmetic_and_ids_close(tmp_path: Path) -> None:
    root = write_source(
        tmp_path,
        """
        const first = () => {};
        export function Fixture() { return <><button onClick={first}>One</button><button>Two</button></>; }
        """,
    )
    ledger = MOD.build_ledger(root)
    coverage = ledger["coverage"]
    assert coverage["discovered_manifestations"] == 2
    assert coverage["classified_manifestations"] == 2
    assert sum(coverage["by_final_state"].values()) == 2
    assert ledger["invariants"] == {
        "arithmetic_closure": True,
        "manifestation_id_unique": True,
        "duplicate_manifestation_ids": 0,
        "unknown_final_states": [],
        "pass": True,
    }


def test_manifestations_are_deterministically_ordered(tmp_path: Path) -> None:
    root = write_source(
        tmp_path,
        "export function Fixture() { return <><button>B</button><button>A</button></>; }",
    )
    first = MOD.build_ledger(root)
    second = MOD.build_ledger(root)
    a = [(x["source_path"], x["line"], x["manifestation_id"]) for x in first["capabilities"]]
    b = [(x["source_path"], x["line"], x["manifestation_id"]) for x in second["capabilities"]]
    assert a == b
