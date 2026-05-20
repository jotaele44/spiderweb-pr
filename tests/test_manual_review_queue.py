"""Tests for ManualReviewQueue in manual_review_queue.py."""

import csv

import pytest

from manual_review_queue import EXPORT_FIELDNAMES, QUEUE_TYPES, ManualReviewQueue


# ── add_item ──────────────────────────────────────────────────────────────────

def test_add_item_returns_uuid(tmp_path):
    q = ManualReviewQueue(str(tmp_path))
    item_id = q.add_item("route_georef", "/img/a.jpg", "bad georef")
    assert isinstance(item_id, str) and len(item_id) == 36


def test_add_item_invalid_type_raises(tmp_path):
    q = ManualReviewQueue(str(tmp_path))
    with pytest.raises(ValueError):
        q.add_item("invalid_type", "/img/a.jpg", "reason")


def test_add_item_all_valid_queue_types_accepted(tmp_path):
    q = ManualReviewQueue(str(tmp_path))
    for qt in QUEUE_TYPES:
        item_id = q.add_item(qt, f"/img/{qt}.jpg", "test")
        assert isinstance(item_id, str)


def test_add_item_duplicate_pending_idempotent(tmp_path):
    q = ManualReviewQueue(str(tmp_path))
    id1 = q.add_item("ocr_correction", "/img/b.jpg", "bad ocr")
    id2 = q.add_item("ocr_correction", "/img/b.jpg", "bad ocr again")
    assert id1 == id2
    assert len(q.get_pending()) == 1


def test_add_item_with_metadata(tmp_path):
    q = ManualReviewQueue(str(tmp_path))
    q.add_item("quality_issue", "/img/c.jpg", "blurry", metadata={"confidence": 0.3})
    items = q.get_pending()
    assert len(items) == 1
    assert items[0]["metadata"] is not None


# ── get_pending ───────────────────────────────────────────────────────────────

def test_get_pending_returns_added_item(tmp_path):
    q = ManualReviewQueue(str(tmp_path))
    q.add_item("quality_issue", "/img/x.jpg", "blurry")
    pending = q.get_pending()
    assert len(pending) == 1
    assert pending[0]["image_path"] == "/img/x.jpg"
    assert pending[0]["status"] == "pending"


def test_get_pending_filtered_by_type(tmp_path):
    q = ManualReviewQueue(str(tmp_path))
    q.add_item("route_georef", "/img/a.jpg", "r1")
    q.add_item("ocr_correction", "/img/b.jpg", "r2")
    assert len(q.get_pending("route_georef")) == 1
    assert len(q.get_pending("ocr_correction")) == 1


# ── mark_reviewed ─────────────────────────────────────────────────────────────

def test_mark_reviewed_transitions_to_reviewed(tmp_path):
    q = ManualReviewQueue(str(tmp_path))
    item_id = q.add_item("coord_calibration", "/img/d.jpg", "drift")
    assert q.mark_reviewed(item_id, "corrected", "Fixed manually") is True
    assert len(q.get_pending()) == 0
    reviewed = q.get_all(status="reviewed")
    assert len(reviewed) == 1
    assert reviewed[0]["resolution"] == "corrected"


def test_mark_reviewed_nonexistent_returns_false(tmp_path):
    q = ManualReviewQueue(str(tmp_path))
    assert q.mark_reviewed("nonexistent-uuid", "ok") is False


# ── mark_flagged ──────────────────────────────────────────────────────────────

def test_mark_flagged_transitions_to_flagged(tmp_path):
    q = ManualReviewQueue(str(tmp_path))
    item_id = q.add_item("quality_issue", "/img/e.jpg", "dark")
    assert q.mark_flagged(item_id, "Unrecoverable") is True
    flagged = q.get_all(status="flagged")
    assert len(flagged) == 1


# ── export_csv ────────────────────────────────────────────────────────────────

def test_export_csv_creates_file(tmp_path):
    q = ManualReviewQueue(str(tmp_path))
    q.add_item("route_georef", "/img/a.jpg", "test")
    csv_path = q.export_csv()
    assert Path(csv_path).exists()


def test_export_csv_has_correct_columns(tmp_path):
    q = ManualReviewQueue(str(tmp_path))
    q.add_item("route_georef", "/img/a.jpg", "test")
    csv_path = q.export_csv()
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        assert set(EXPORT_FIELDNAMES).issubset(set(reader.fieldnames or []))
        rows = list(reader)
    assert len(rows) == 1


def test_export_csv_filtered_by_type(tmp_path):
    q = ManualReviewQueue(str(tmp_path))
    q.add_item("route_georef", "/img/a.jpg", "r1")
    q.add_item("ocr_correction", "/img/b.jpg", "r2")
    csv_path = q.export_csv(queue_type="route_georef")
    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1


# ── get_stats ─────────────────────────────────────────────────────────────────

def test_get_stats_returns_total(tmp_path):
    q = ManualReviewQueue(str(tmp_path))
    q.add_item("route_georef", "/img/a.jpg", "r1")
    q.add_item("route_georef", "/img/b.jpg", "r2")
    stats = q.get_stats()
    assert stats["_total"] == 2
    assert stats["route_georef"]["pending"] == 2


def test_get_stats_mixed_statuses(tmp_path):
    q = ManualReviewQueue(str(tmp_path))
    id1 = q.add_item("quality_issue", "/img/a.jpg", "r")
    q.add_item("quality_issue", "/img/b.jpg", "r")
    q.mark_reviewed(id1, "ok")
    stats = q.get_stats()
    assert stats["quality_issue"].get("pending") == 1
    assert stats["quality_issue"].get("reviewed") == 1


# ── get_all ───────────────────────────────────────────────────────────────────

def test_get_all_returns_items_across_statuses(tmp_path):
    from pathlib import Path as _Path
    q = ManualReviewQueue(str(tmp_path))
    id1 = q.add_item("quality_issue", "/img/x.jpg", "r")
    q.add_item("quality_issue", "/img/y.jpg", "r")
    q.mark_reviewed(id1, "ok")
    assert len(q.get_all()) == 2


# ── Path import for export_csv test ──────────────────────────────────────────
from pathlib import Path
