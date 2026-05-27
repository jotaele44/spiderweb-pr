"""Tests for prepare_data.py: clean_rows, to_chunks, to_finetune, load_csv."""

import csv
import json
from pathlib import Path

import pytest

from llm.prepare_data import (
    MIN_TEXT_LENGTH,
    clean_rows,
    load_csv,
    to_chunks,
    to_finetune,
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
