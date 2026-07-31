"""Tests for the unlabeled-RLSM parallel runner harness (T4-24 / T4-41).

The OCR worker is injected, so the parallelism harness (discovery, dedup, the
batch loop, the thread-safe write path) is exercised here with a deterministic
mock — no pytesseract/opencv required.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import scripts.rlsm_unlabeled as rl


class MockWorker:
    """process(path) -> data, or None to signal 'skip', or raise to signal 'err'."""

    def __init__(self, skip_paths=(), fail_paths=()):
        self.skip = set(skip_paths)
        self.fail = set(fail_paths)
        self.seen: list[str] = []

    def process(self, path_str: str):
        self.seen.append(path_str)
        if path_str in self.fail:
            raise RuntimeError("boom")
        if path_str in self.skip:
            return None
        return {"extracted": path_str}


def _img(tmp_path, name, content: bytes) -> str:
    p = tmp_path / name
    p.write_bytes(content)
    return str(p)


def _db_with_screenshots(tmp_path) -> str:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE screenshots (screenshot_id TEXT PRIMARY KEY, image_path TEXT)")
    conn.commit()
    conn.close()
    return str(db)


def test_run_batch_processes_all_paths(tmp_path):
    db = _db_with_screenshots(tmp_path)
    paths = [_img(tmp_path, f"a{i}.png", bytes([i, i + 1])) for i in range(5)]
    writes: list[dict] = []
    stats = rl.run_batch(paths, db, MockWorker(), workers=4, store=writes.append)
    assert stats["processed"] == 5
    assert (stats["ok"], stats["skip"], stats["err"]) == (5, 0, 0)
    assert {w["path"] for w in writes} == set(paths)


def test_run_batch_counts_skip_and_err(tmp_path):
    db = _db_with_screenshots(tmp_path)
    ok = _img(tmp_path, "ok.png", b"\x01")
    skip = _img(tmp_path, "skip.png", b"\x02")
    fail = _img(tmp_path, "fail.png", b"\x03")
    writes: list[dict] = []
    stats = rl.run_batch([ok, skip, fail], db, MockWorker(skip_paths=[skip], fail_paths=[fail]),
                         workers=2, store=writes.append)
    assert (stats["ok"], stats["skip"], stats["err"]) == (1, 1, 1)
    assert [w["path"] for w in writes] == [ok]  # only the ok result is stored


def test_run_batch_dedups_already_processed(tmp_path):
    db = _db_with_screenshots(tmp_path)
    img = _img(tmp_path, "dup.png", b"hello-world")
    sha = rl._sha256(Path(img))
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO screenshots (screenshot_id, image_path) VALUES (?, ?)", (sha, img))
    conn.commit()
    conn.close()
    worker = MockWorker()
    stats = rl.run_batch([img], db, worker, store=lambda r: None)
    assert (stats["ok"], stats["skip"], stats["err"]) == (0, 1, 0)
    assert worker.seen == []  # deduped image never reaches the worker


def test_process_one_missing_file_is_err(tmp_path):
    db = _db_with_screenshots(tmp_path)
    res = rl.process_one(str(tmp_path / "nope.png"), db, MockWorker())
    assert res["status"] == "err"


def test_process_one_handles_missing_screenshots_table(tmp_path):
    # A DB without the screenshots table must not crash the dedup check.
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    img = _img(tmp_path, "x.png", b"\x09")
    res = rl.process_one(img, str(db), MockWorker())
    assert res["status"] == "ok"


def test_discover_images_recursive_and_filtered(tmp_path):
    (tmp_path / "sub").mkdir()
    img = tmp_path / "sub" / "x.PNG"
    img.write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("ignore me")
    assert rl.discover_images(tmp_path) == [str(img)]


def test_discover_images_missing_dir():
    assert rl.discover_images("/no/such/dir/here") == []


def test_status_cli_reports_count(tmp_path, capsys):
    db = _db_with_screenshots(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO screenshots (screenshot_id, image_path) VALUES ('s1', 'a.png')")
    conn.commit()
    conn.close()
    rc = rl.main(["--status", "--db", db])
    assert rc == 0
    assert "screenshots processed: 1" in capsys.readouterr().out


def test_run_all_print_rlsm_status(tmp_path, capsys):
    from pipeline.flight_analyzer import FlightDatabase
    import run_all

    db = str(tmp_path / "flights.db")
    FlightDatabase(db)  # creates the screenshots table
    run_all.print_rlsm_status(db)
    out = capsys.readouterr().out
    assert "RLSM STATUS" in out
    assert "Screenshots processed" in out
