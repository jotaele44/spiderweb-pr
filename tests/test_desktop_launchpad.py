"""Spiderweb's Launch Pad declaration (desktop/config.py).

The screen itself lives in the shared prii_desktop runtime; these tests keep the
declaration true to this repository. They skip when the installed runtime
predates the Launch Pad.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

launchpad = pytest.importorskip("prii_desktop.launchpad")

from prii_desktop import DesktopConfig  # noqa: E402

from desktop import config  # noqa: E402

ROOT = Path(config.REPO_ROOT)


def _spec():
    return launchpad.launchpad_spec(DesktopConfig.from_module(config))


def test_declaration_is_valid_two_mode_with_one_start_page():
    spec = _spec()
    assert spec is not None and spec.has_modes
    assert spec.operator.token_env is None
    # No URL router: a second start page would have nothing to open.
    assert [page.route for page in spec.start_pages] == ["/"]
    assert "react-router" not in (ROOT / "server/frontend/package.json").read_text()


def test_guest_allow_list_is_exactly_the_read_only_post():
    backend = "\n".join(
        (ROOT / "server/backend" / name).read_text()
        for name in ("main.py", "eri_imagery.py", "access_points_api.py")
    )
    declared = re.findall(
        r'@(?:app|router)\.(post|put|patch|delete)\(\s*"([^"]+)"', backend
    )
    assert sorted(declared) == [
        ("delete", "/pipeline/{job_id}"),
        ("post", "/pipeline/run"),
        ("post", "/rag/index"),
        ("post", "/rag/query"),
    ]  # a new non-GET route must be classified here
    guard = launchpad.GuestGuard(None, _spec().guest_allow)
    passes = [
        (method, path)
        for method, path in sorted(declared)
        if any(
            (allowed is None or allowed == method.upper())
            and pattern.fullmatch(re.sub(r"\{[^}]+\}", "x", path))
            for allowed, pattern in guard.allow
        )
    ]
    assert passes == [("post", "/rag/query")]


def test_option_binds_a_variable_the_query_model_reads():
    code = (ROOT / "llm/query_llm.py").read_text()
    for option in _spec().options:
        assert f'"{option.env}"' in code, option.env


def test_status_counts_the_workspace_database(tmp_path, monkeypatch):
    monkeypatch.setenv(config.DATA_ENV_VAR, str(tmp_path))
    missing = config._launchpad_status()[0]
    assert missing["value"] == "Missing" and missing["status"] == "warn"
    assert list(tmp_path.iterdir()) == []  # a readiness check creates nothing

    (tmp_path / "server").mkdir()
    conn = sqlite3.connect(tmp_path / "server" / "priis.db")
    for table, rows in (("contracts", 2), ("sites", 1), ("anomalies", 0)):
        conn.execute(f"CREATE TABLE {table} (id INTEGER)")
        conn.executemany(f"INSERT INTO {table} VALUES (?)", [(i,) for i in range(rows)])
    conn.commit()
    conn.close()
    loaded = config._launchpad_status()[0]
    assert loaded["value"] == "3 records" and loaded["status"] == "pass"
    assert "2 contracts, 1 sites and 0 anomalies" in loaded["detail"]


@pytest.mark.parametrize("name", ["workspace#1", "what?ws", "with space"])
def test_status_reads_a_workspace_whose_path_has_uri_characters(
    tmp_path, monkeypatch, name
):
    home = tmp_path / name
    (home / "server").mkdir(parents=True)
    monkeypatch.setenv(config.DATA_ENV_VAR, str(home))
    conn = sqlite3.connect(home / "server" / "priis.db")
    for table in ("contracts", "sites", "anomalies"):
        conn.execute(f"CREATE TABLE {table} (id INTEGER)")
    conn.execute("INSERT INTO contracts VALUES (1)")
    conn.commit()
    conn.close()
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))

    row = config._launchpad_status()[0]

    assert row["value"] == "1 records" and row["status"] == "pass"
    # Read-only, at the right file: nothing appears anywhere under tmp_path.
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before


def test_status_reports_an_unreadable_database(tmp_path, monkeypatch):
    monkeypatch.setenv(config.DATA_ENV_VAR, str(tmp_path))
    (tmp_path / "server").mkdir()
    conn = sqlite3.connect(tmp_path / "server" / "priis.db")
    conn.execute("CREATE TABLE unrelated (id INTEGER)")
    conn.commit()
    conn.close()
    row = config._launchpad_status()[0]
    assert row["value"] == "Unreadable" and row["status"] == "fail"
