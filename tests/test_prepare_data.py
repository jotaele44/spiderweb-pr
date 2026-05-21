"""Tests for prepare_data.py: clean_rows, to_chunks, to_finetune, load_csv."""

import csv
import json
from pathlib import Path

import pytest

from prepare_data import (
    MIN_TEXT_LENGTH,
    REQUIRED_CSV_COLUMNS,
    clean_rows,
    deduplicate,
    export_stats,
    load_csv,
    split,
    to_chunks,
    to_finetune,
    validate_source,
)


# ------------------------------------------------------------------ helpers

def _make_row(**kwargs):
    defaults = {
        "id": "post1",
        "title": "Strange lights over Aguadilla airport",
        "text": "Witnesses reported hovering craft with no sound.",
        "subreddit": "UFOs",
        "keyword": "UAP",
        "url": "https://reddit.com/r/UFOs/post1",
        "created": "2024-01-15T22:30:00Z",
        "comments": "12",
        "score": "45",
    }
    defaults.update(kwargs)
    return defaults


def _make_csv(tmp_path, rows):
    p = tmp_path / "test.csv"
    fieldnames = ["id", "title", "text", "subreddit", "keyword", "url", "created", "comments", "score"]
    with open(p, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return str(p)


# ------------------------------------------------------------------ load_csv

def test_load_csv_returns_list_of_dicts(tmp_path):
    path = _make_csv(tmp_path, [_make_row()])
    rows = load_csv(path)
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert "id" in rows[0]


def test_load_csv_multiple_rows(tmp_path):
    rows = [_make_row(id=f"p{i}", title=f"Title {i} " * 5) for i in range(5)]
    path = _make_csv(tmp_path, rows)
    loaded = load_csv(path)
    assert len(loaded) == 5


def test_load_csv_unicode(tmp_path):
    row = _make_row(title="Luces extrañas sobre Rincón — OVNI reportado")
    path = _make_csv(tmp_path, [row])
    loaded = load_csv(path)
    assert "extrañas" in loaded[0]["title"]


# ------------------------------------------------------------------ clean_rows

def test_clean_rows_keeps_valid_row():
    rows = [_make_row()]
    result = clean_rows(rows)
    assert len(result) == 1


def test_clean_rows_deduplicates_by_id():
    rows = [_make_row(id="dup"), _make_row(id="dup", title="Different title")]
    result = clean_rows(rows)
    assert len(result) == 1


def test_clean_rows_drops_short_content():
    rows = [_make_row(title="Short", text="")]
    result = clean_rows(rows)
    assert len(result) == 0


def test_clean_rows_respects_min_text_length():
    long_title = "X" * MIN_TEXT_LENGTH
    rows = [_make_row(title=long_title, text="")]
    result = clean_rows(rows)
    assert len(result) == 1


def test_clean_rows_casts_numeric_fields():
    rows = [_make_row(comments="99", score="150")]
    result = clean_rows(rows)
    assert result[0]["comments"] == 99
    assert result[0]["score"] == 150


def test_clean_rows_handles_empty_numeric_fields():
    rows = [_make_row(comments="", score="")]
    result = clean_rows(rows)
    assert result[0]["comments"] == 0
    assert result[0]["score"] == 0


def test_clean_rows_empty_input():
    assert clean_rows([]) == []


# ------------------------------------------------------------------ to_chunks

def test_to_chunks_creates_file(tmp_path):
    rows = [clean_rows([_make_row()])[0]]
    out = str(tmp_path / "chunks.jsonl")
    to_chunks(rows, out)
    assert Path(out).exists()


def test_to_chunks_valid_jsonl(tmp_path):
    rows = [clean_rows([_make_row(id=f"p{i}")])[0] for i in range(3)]
    out = str(tmp_path / "chunks.jsonl")
    to_chunks(rows, out)
    lines = Path(out).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    for line in lines:
        obj = json.loads(line)
        assert "id" in obj and "text" in obj and "metadata" in obj


def test_to_chunks_text_combines_title_and_body(tmp_path):
    row = clean_rows([_make_row(title="Lights spotted over the bay", text="Witnesses described a hovering craft.")])[0]
    out = str(tmp_path / "chunks.jsonl")
    to_chunks([row], out)
    obj = json.loads(Path(out).read_text())
    assert "Lights spotted over the bay" in obj["text"]
    assert "hovering craft" in obj["text"]


def test_to_chunks_metadata_keys(tmp_path):
    row = clean_rows([_make_row()])[0]
    out = str(tmp_path / "chunks.jsonl")
    to_chunks([row], out)
    meta = json.loads(Path(out).read_text())["metadata"]
    for key in ("subreddit", "keyword", "url", "created", "score", "comments"):
        assert key in meta, f"Missing metadata key: {key}"


def test_to_chunks_unicode_preserved(tmp_path):
    row = clean_rows([_make_row(title="Año nuevo con OVNIs sobre Ponce")])[0]
    out = str(tmp_path / "chunks.jsonl")
    to_chunks([row], out)
    text = Path(out).read_text(encoding="utf-8")
    assert "OVNIs" in text


# ------------------------------------------------------------------ to_finetune

def test_to_finetune_creates_file(tmp_path):
    rows = [clean_rows([_make_row()])[0]]
    out = str(tmp_path / "finetune.jsonl")
    to_finetune(rows, out)
    assert Path(out).exists()


def test_to_finetune_valid_jsonl(tmp_path):
    rows = [clean_rows([_make_row(id=f"p{i}")])[0] for i in range(2)]
    out = str(tmp_path / "finetune.jsonl")
    to_finetune(rows, out)
    lines = Path(out).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        obj = json.loads(line)
        assert "prompt" in obj and "completion" in obj


def test_to_finetune_prompt_contains_subreddit(tmp_path):
    row = clean_rows([_make_row(subreddit="HighStrangeness")])[0]
    out = str(tmp_path / "finetune.jsonl")
    to_finetune([row], out)
    obj = json.loads(Path(out).read_text())
    assert "HighStrangeness" in obj["prompt"]


def test_to_finetune_completion_contains_title(tmp_path):
    row = clean_rows([_make_row(title="Lights near Arecibo observatory")])[0]
    out = str(tmp_path / "finetune.jsonl")
    to_finetune([row], out)
    obj = json.loads(Path(out).read_text())
    assert "Lights near Arecibo observatory" in obj["completion"]


# ── Task 137: validate_source ─────────────────────────────────────────────────

def test_validate_source_valid_csv(tmp_path):
    csv_path = _make_csv(tmp_path, [_make_row()])
    validate_source(str(csv_path))  # should not raise


def test_validate_source_missing_file():
    with pytest.raises(FileNotFoundError):
        validate_source("/nonexistent/path/PRUAP.csv")


def test_validate_source_missing_required_column(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("title,text\nfoo,bar\n")
    with pytest.raises(ValueError, match="missing required columns"):
        validate_source(str(bad))


def test_validate_source_all_required_cols_defined():
    assert REQUIRED_CSV_COLUMNS == {"id", "title", "subreddit"}


# ── Task 138: deduplicate ─────────────────────────────────────────────────────

def test_deduplicate_by_id_removes_duplicates():
    rows = clean_rows([_make_row(id="x"), _make_row(id="x"), _make_row(id="y")])
    result = deduplicate(rows, strategy="id")
    assert len(result) == 2


def test_deduplicate_by_id_keeps_order():
    r1 = clean_rows([_make_row(id="a")])[0]
    r2 = clean_rows([_make_row(id="b")])[0]
    result = deduplicate([r1, r2], strategy="id")
    assert [r["id"] for r in result] == ["a", "b"]


def test_deduplicate_by_hash_removes_same_content():
    rows = clean_rows([
        _make_row(id="p1", title="Same title", text="Same text same text same text."),
        _make_row(id="p2", title="Same title", text="Same text same text same text."),
    ])
    result = deduplicate(rows, strategy="hash")
    assert len(result) == 1


def test_deduplicate_by_both():
    rows = clean_rows([_make_row(id="z"), _make_row(id="z")])
    result = deduplicate(rows, strategy="both")
    assert len(result) == 1


def test_deduplicate_invalid_strategy():
    with pytest.raises(ValueError, match="Unknown dedup strategy"):
        deduplicate([], strategy="bogus")


# ── export_stats ──────────────────────────────────────────────────────────────

def test_export_stats_structure():
    rows = clean_rows([_make_row(subreddit="UFOs"), _make_row(id="p2", subreddit="NUFORC")])
    stats = export_stats(rows)
    assert set(stats.keys()) == {"total", "by_subreddit", "avg_tokens", "min_tokens", "max_tokens"}


def test_export_stats_total():
    rows = clean_rows([_make_row(), _make_row(id="p2")])
    assert export_stats(rows)["total"] == 2


def test_export_stats_by_subreddit():
    rows = clean_rows([
        _make_row(subreddit="UFOs"),
        _make_row(id="p2", subreddit="UFOs"),
        _make_row(id="p3", subreddit="NUFORC"),
    ])
    stats = export_stats(rows)
    assert stats["by_subreddit"]["UFOs"] == 2
    assert stats["by_subreddit"]["NUFORC"] == 1


def test_export_stats_empty():
    stats = export_stats([])
    assert stats["total"] == 0
    assert stats["avg_tokens"] == 0


# ── Task 123: split() ─────────────────────────────────────────────────────────

def _make_rows(n=20):
    rows = []
    subs = ["UFOs", "NUFORC", "conspiracy"]
    for i in range(n):
        rows.append(_make_row(
            id=f"p{i}",
            subreddit=subs[i % len(subs)],
        ))
    return rows


def test_split_sizes_sum_to_total():
    rows = _make_rows(20)
    train, val, test = split(rows, train_ratio=0.8, val_ratio=0.1)
    assert len(train) + len(val) + len(test) == len(rows)


def test_split_train_is_largest():
    rows = _make_rows(20)
    train, val, test = split(rows)
    assert len(train) >= len(val)
    assert len(train) >= len(test)


def test_split_no_overlap():
    rows = _make_rows(30)
    train, val, test = split(rows)
    all_ids = [r["id"] for r in train + val + test]
    assert len(all_ids) == len(set(all_ids)), "No row should appear in multiple splits"


def test_split_rejects_bad_ratios():
    import pytest
    rows = _make_rows(10)
    with pytest.raises(ValueError):
        split(rows, train_ratio=0.9, val_ratio=0.15)  # sum > 1.0
    with pytest.raises(ValueError):
        split(rows, train_ratio=0.0, val_ratio=0.5)   # train_ratio = 0
