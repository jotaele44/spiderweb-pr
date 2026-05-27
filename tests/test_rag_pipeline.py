"""Tests for rag_pipeline.py: format_context, get_collection, build_index stub."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys

import pytest

from llm.rag_pipeline import format_context, COLLECTION_NAME, DEFAULT_TOP_K


# ------------------------------------------------------------------ helpers

def _make_hit(i=1, subreddit="UFOs", text="Hovering craft seen near the coast.",
              url="https://reddit.com/r/UFOs/comments/abc", score=0.92):
    return {
        "text": text,
        "metadata": {
            "subreddit": subreddit,
            "created": "2024-03-10T18:00:00Z",
            "score": 42,
            "url": url,
        },
        "score": score,
    }


# ------------------------------------------------------------------ format_context

def test_format_context_empty_hits():
    result = format_context([])
    assert result == ""


def test_format_context_single_hit():
    hit = _make_hit()
    result = format_context([hit])
    assert "[1]" in result
    assert "UFOs" in result
    assert hit["text"] in result


def test_format_context_multiple_hits_separated():
    hits = [_make_hit(i=i, subreddit=f"sub{i}") for i in range(3)]
    result = format_context(hits)
    assert "[1]" in result
    assert "[2]" in result
    assert "[3]" in result
    assert "---" in result


def test_format_context_contains_url():
    hit = _make_hit(url="https://reddit.com/r/UFOs/comments/xyz123")
    result = format_context([hit])
    assert "xyz123" in result


def test_format_context_contains_date():
    hit = _make_hit()
    result = format_context([hit])
    assert "2024-03-10" in result


def test_format_context_contains_score_label():
    hit = _make_hit()
    result = format_context([hit])
    assert "score=" in result


def test_format_context_hit_text_in_output():
    unique_text = "Triangular craft with amber lights observed at 0300 local time."
    hit = _make_hit(text=unique_text)
    result = format_context([hit])
    assert unique_text in result


def test_format_context_missing_metadata_keys_graceful():
    hit = {"text": "Some sighting text here reported by locals.", "metadata": {}, "score": 0.5}
    result = format_context([hit])
    assert "[1]" in result
    assert "?" in result  # fallback for missing keys


# ------------------------------------------------------------------ get_collection (mocked)

def test_get_collection_uses_collection_name(tmp_path):
    chromadb = pytest.importorskip("chromadb")
    from llm.rag_pipeline import get_collection
    col = get_collection(str(tmp_path / "chroma_test"))
    assert col.name == COLLECTION_NAME


def test_get_collection_idempotent(tmp_path):
    chromadb = pytest.importorskip("chromadb")
    from llm.rag_pipeline import get_collection
    db = str(tmp_path / "chroma_idem")
    col1 = get_collection(db)
    col2 = get_collection(db)
    assert col1.name == col2.name


# ------------------------------------------------------------------ build_index (mocked)

def test_build_index_missing_chunks_file(tmp_path, capsys):
    import sys
    from unittest.mock import MagicMock
    fake_st = MagicMock()
    with patch.dict(sys.modules, {"sentence_transformers": fake_st}):
        from llm.rag_pipeline import build_index
        with pytest.raises(SystemExit):
            build_index(str(tmp_path / "nonexistent.jsonl"), str(tmp_path / "db"))


def test_build_index_calls_upsert(tmp_path):
    chromadb = pytest.importorskip("chromadb")
    chunks_path = tmp_path / "chunks.jsonl"
    chunks = [
        {"id": f"p{i}", "text": f"Post number {i} about UAP sighting in Puerto Rico coast.",
         "metadata": {"subreddit": "UFOs", "keyword": "UAP", "url": "", "created": "", "score": 0, "comments": 0}}
        for i in range(3)
    ]
    chunks_path.write_text("\n".join(json.dumps(c) for c in chunks), encoding="utf-8")

    mock_model = MagicMock()
    mock_model.encode.return_value = [[0.1] * 384] * 3

    with patch("rag_pipeline.SentenceTransformer", return_value=mock_model):
        from llm.rag_pipeline import build_index
        build_index(str(chunks_path), str(tmp_path / "db"))

    mock_model.encode.assert_called_once()


# ------------------------------------------------------------------ retrieve (mocked)

def test_retrieve_returns_hits(tmp_path):
    chromadb = pytest.importorskip("chromadb")
    from llm.rag_pipeline import get_collection, retrieve

    db = str(tmp_path / "chroma_retrieve")
    col = get_collection(db)
    col.add(
        ids=["p1"],
        documents=["UAP sighting over Laguna del Condado"],
        embeddings=[[0.1] * 10],
        metadatas=[{"subreddit": "UFOs", "keyword": "UAP", "url": "", "created": "2024-01-01", "score": 5, "comments": 2}],
    )

    mock_model = MagicMock()
    mock_model.encode.return_value = [[0.1] * 10]

    with patch("rag_pipeline.SentenceTransformer", return_value=mock_model):
        hits = retrieve("UAP sighting", db, top_k=1)

    assert len(hits) == 1
    assert "text" in hits[0]
    assert "score" in hits[0]
    assert "metadata" in hits[0]


def test_retrieve_score_in_range(tmp_path):
    chromadb = pytest.importorskip("chromadb")
    from llm.rag_pipeline import get_collection, retrieve

    db = str(tmp_path / "chroma_score")
    col = get_collection(db)
    col.add(
        ids=["p1"],
        documents=["Some post about Puerto Rico lights"],
        embeddings=[[0.5] * 10],
        metadatas=[{"subreddit": "UFOs", "keyword": "UAP", "url": "", "created": "", "score": 1, "comments": 0}],
    )

    mock_model = MagicMock()
    mock_model.encode.return_value = [[0.5] * 10]

    with patch("rag_pipeline.SentenceTransformer", return_value=mock_model):
        hits = retrieve("lights", db, top_k=1)

    assert 0.0 <= hits[0]["score"] <= 1.0


def test_retrieve_from_empty_corpus_returns_list(tmp_path):
    chromadb = pytest.importorskip("chromadb")
    from unittest.mock import MagicMock, patch

    mock_model = MagicMock()
    mock_model.encode.return_value = [[0.5] * 10]

    with patch("rag_pipeline.SentenceTransformer", return_value=mock_model):
        from llm.rag_pipeline import retrieve
        results = retrieve("any query", str(tmp_path / "empty_db"), top_k=5)

    assert isinstance(results, list)


# ── Phase 6: RAG hardening ────────────────────────────────────────────────────

def test_safe_retrieve_returns_list_on_import_error():
    from llm.rag_pipeline import safe_retrieve
    results = safe_retrieve("query", "/nonexistent/path", top_k=3)
    assert isinstance(results, list)


def test_validate_hits_filters_incomplete():
    from llm.rag_pipeline import validate_hits
    good = {"text": "t", "metadata": {}, "score": 0.9}
    bad = {"text": "t", "score": 0.5}  # missing metadata
    result = validate_hits([good, bad])
    assert len(result) == 1
    assert result[0] is good


def test_validate_hits_empty_input():
    from llm.rag_pipeline import validate_hits
    assert validate_hits([]) == []


def test_chunk_text_basic():
    from llm.rag_pipeline import chunk_text
    text = "A" * 1000
    chunks = chunk_text(text, max_chars=100, overlap=10)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 100


def test_chunk_text_empty_returns_empty():
    from llm.rag_pipeline import chunk_text
    assert chunk_text("") == []


def test_chunk_text_short_text_single_chunk():
    from llm.rag_pipeline import chunk_text
    assert chunk_text("hello world", max_chars=512) == ["hello world"]


def test_chunk_text_invalid_max_chars_raises():
    from llm.rag_pipeline import chunk_text
    import pytest
    with pytest.raises(ValueError):
        chunk_text("text", max_chars=0)


def test_format_context_with_limit_truncates():
    from llm.rag_pipeline import format_context_with_limit
    long_hit = _make_hit(text="X" * 5000)
    result = format_context_with_limit([long_hit], max_chars=100)
    assert len(result) <= 120  # max_chars + truncation marker
    assert "truncated" in result


def test_format_context_with_limit_no_truncation_for_short():
    from llm.rag_pipeline import format_context_with_limit
    hit = _make_hit(text="short text")
    result = format_context_with_limit([hit], max_chars=10000)
    assert "truncated" not in result
