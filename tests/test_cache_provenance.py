"""Rerunning a fetch keeps the cache's earlier acquisition records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from source_adapters.cache_provenance import merge_rows, previous_rows
from source_adapters.nasa_srtmgl1 import cli as srtm_cli
from source_adapters.opentopography_globaldem import cli as ot_cli


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _downloaded(name: str, data: bytes, when: str) -> dict:
    return {"file_name": name, "sha256": _sha(data), "file_size_bytes": len(data),
            "accessed_at": when, "final_host": "cdn.example", "review_status": "downloaded_local"}


def test_cache_hit_keeps_the_original_download_record(tmp_path: Path) -> None:
    (tmp_path / "a.zip").write_bytes(b"a")
    first = [_downloaded("a.zip", b"a", "2026-11-23T00:00:00Z")]
    hit = {"file_name": "a.zip", "sha256": _sha(b"a"), "accessed_at": None, "final_host": None,
           "review_status": "cached_local", "tile_id": "N18W067"}
    (row,) = merge_rows(first, [hit], tmp_path)
    assert row["accessed_at"] == "2026-11-23T00:00:00Z" and row["final_host"] == "cdn.example"
    assert row["tile_id"] == "N18W067"


def test_changed_bytes_are_not_given_the_old_record(tmp_path: Path) -> None:
    first = [_downloaded("a.zip", b"a", "2026-11-23T00:00:00Z")]
    hit = {"file_name": "a.zip", "sha256": _sha(b"b"), "accessed_at": None, "review_status": "cached_local"}
    (row,) = merge_rows(first, [hit], tmp_path)
    assert row["accessed_at"] is None


def test_rows_outside_the_selection_survive_while_cached(tmp_path: Path) -> None:
    (tmp_path / "kept.zip").write_bytes(b"k")
    (tmp_path / "changed.zip").write_bytes(b"new")
    first = [_downloaded("kept.zip", b"k", "t1"), _downloaded("changed.zip", b"old", "t1"),
             _downloaded("gone.zip", b"g", "t1")]
    rows = merge_rows(first, [_downloaded("new.zip", b"n", "t2")], tmp_path)
    assert [r["file_name"] for r in rows] == ["kept.zip", "new.zip"]


def test_previous_rows_tolerates_a_missing_file(tmp_path: Path) -> None:
    assert previous_rows(tmp_path / "provenance.json") == []


def test_srtm_num_only_rerun_keeps_height_records(tmp_path: Path, monkeypatch) -> None:
    def fake_download(url, dest, **kwargs):
        dest.write_bytes(dest.name.encode())
        return {"source_url": url, "final_host": "cdn.example", "accessed_at": "2026-11-23T00:00:00Z",
                "file_name": dest.name, "file_size_bytes": len(dest.name), "sha256": _sha(dest.name.encode()),
                "raw_commit_allowed": False}

    monkeypatch.setattr(srtm_cli, "download", fake_download)
    args = ["fetch", "--tile", "N18W067", "--cache-dir", str(tmp_path), "--acknowledge-no-commit"]
    assert srtm_cli.main(args) == 0
    assert srtm_cli.main(args + ["--num-only"]) == 0
    files = json.loads((tmp_path / "provenance.json").read_text())["files"]
    assert [(f["product"], f["review_status"], f["accessed_at"]) for f in files] == [
        ("SRTMGL1", "downloaded_local", "2026-11-23T00:00:00Z"),
        ("SRTMGL1N", "downloaded_local", "2026-11-23T00:00:00Z"),
    ]


def test_opentopography_second_demtype_keeps_the_first(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENTOPOGRAPHY_API_KEY", "unused")

    def fake_fetch(config, demtype, bbox, dest, **kwargs):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(demtype.encode())
        return {"demtype": demtype, "file_name": dest.name, "file_size_bytes": len(demtype),
                "sha256": _sha(demtype.encode()), "accessed_at": "t", "raw_commit_allowed": False}

    monkeypatch.setattr(ot_cli, "fetch", fake_fetch)
    for demtype in ("COP30", "AW3D30"):
        assert ot_cli.main(["fetch", "--demtype", demtype, "--cache-dir", str(tmp_path), "--acknowledge-no-commit"]) == 0
    files = json.loads((tmp_path / "provenance.json").read_text())["files"]
    assert sorted(f["demtype"] for f in files) == ["AW3D30", "COP30"]
