"""Tests for query_llm.py: build_prompt, get_context, generate (all mocked)."""

import os
from unittest.mock import MagicMock, patch

import pytest

from query_llm import (
    DEFAULT_DB,
    DEFAULT_MODEL,
    DEFAULT_TOP_K,
    MAX_NEW_TOKENS,
    build_prompt,
    get_context,
    generate,
)


# ------------------------------------------------------------------ build_prompt

def test_build_prompt_no_context_contains_question():
    q = "What UAP sightings exist near Aguadilla?"
    prompt = build_prompt(q)
    assert q in prompt


def test_build_prompt_no_context_no_relevant_posts_section():
    prompt = build_prompt("some question")
    assert "Relevant Posts" not in prompt


def test_build_prompt_with_context_contains_question():
    q = "Are USOs reported near Puerto Rico?"
    ctx = "[1] r/UFOs | 2024-01-10 | score=30\nSome post text here."
    prompt = build_prompt(q, context=ctx)
    assert q in prompt


def test_build_prompt_with_context_contains_context():
    ctx = "[1] r/UFOs | 2024-01-10 | score=30\nPost about hovering lights."
    prompt = build_prompt("question", context=ctx)
    assert ctx in prompt


def test_build_prompt_with_context_contains_relevant_posts_header():
    prompt = build_prompt("question", context="some context text here")
    assert "Relevant Posts" in prompt


def test_build_prompt_with_context_contains_answer_marker():
    prompt = build_prompt("question", context="some ctx")
    assert "### Answer" in prompt


def test_build_prompt_no_context_contains_answer_marker():
    prompt = build_prompt("question")
    assert "### Answer" in prompt


def test_build_prompt_none_context_same_as_no_context():
    prompt_none = build_prompt("question", context=None)
    prompt_bare = build_prompt("question")
    assert prompt_none == prompt_bare


# ------------------------------------------------------------------ get_context

def test_get_context_missing_db_returns_none(tmp_path):
    nonexistent = str(tmp_path / "no_index")
    result = get_context("query text", nonexistent, top_k=3)
    assert result is None


def test_get_context_calls_retrieve_when_db_exists(tmp_path):
    db = tmp_path / "fake_index"
    db.mkdir()

    fake_hits = [
        {
            "text": "Post about UAP near Rincón.",
            "metadata": {"subreddit": "UFOs", "created": "2024-01-01", "score": 10, "url": ""},
            "score": 0.88,
        }
    ]
    # retrieve and format_context are imported inside get_context from rag_pipeline
    with patch("rag_pipeline.retrieve", return_value=fake_hits), \
         patch("rag_pipeline.format_context", return_value="formatted context") as mock_fmt:
        result = get_context("some query", str(db), top_k=3)

    mock_fmt.assert_called_once_with(fake_hits)
    assert result == "formatted context"


def test_get_context_empty_hits_returns_none(tmp_path):
    db = tmp_path / "empty_index"
    db.mkdir()

    with patch("rag_pipeline.retrieve", return_value=[]):
        result = get_context("query", str(db), top_k=5)

    assert result is None


# ------------------------------------------------------------------ generate

def test_generate_decodes_new_tokens_only():
    torch = pytest.importorskip("torch")
    import torch

    tokenizer = MagicMock()
    model = MagicMock()
    model.device = "cpu"

    prompt_ids = torch.tensor([[1, 2, 3, 4, 5]])
    new_ids = torch.tensor([[1, 2, 3, 4, 5, 6, 7]])

    tokenizer.return_value = {"input_ids": prompt_ids}
    tokenizer.eos_token_id = 2
    model.generate.return_value = new_ids
    tokenizer.decode.return_value = "the answer"

    result = generate(tokenizer, model, "test prompt")

    # decode called with only the NEW tokens (indices 5 onwards)
    decoded_arg = tokenizer.decode.call_args[0][0]
    assert list(decoded_arg) == [6, 7]
    assert result == "the answer"


def test_generate_strips_whitespace():
    torch = pytest.importorskip("torch")
    import torch

    tokenizer = MagicMock()
    model = MagicMock()
    model.device = "cpu"

    tokenizer.return_value = {"input_ids": torch.tensor([[1, 2]])}
    tokenizer.eos_token_id = 2
    model.generate.return_value = torch.tensor([[1, 2, 3]])
    tokenizer.decode.return_value = "   answer with spaces   "

    result = generate(tokenizer, model, "prompt")
    assert result == "answer with spaces"


def test_generate_passes_max_new_tokens():
    torch = pytest.importorskip("torch")
    import torch

    tokenizer = MagicMock()
    model = MagicMock()
    model.device = "cpu"

    tokenizer.return_value = {"input_ids": torch.tensor([[1]])}
    tokenizer.eos_token_id = 2
    model.generate.return_value = torch.tensor([[1, 2]])
    tokenizer.decode.return_value = "ok"

    generate(tokenizer, model, "prompt")

    call_kwargs = model.generate.call_args[1]
    assert call_kwargs["max_new_tokens"] == MAX_NEW_TOKENS


# ------------------------------------------------------------------ constants

def test_default_model_is_set():
    assert DEFAULT_MODEL == "google/gemma-2-2b-it"


def test_default_top_k():
    assert DEFAULT_TOP_K == 5


def test_max_new_tokens():
    assert MAX_NEW_TOKENS == 512


def test_build_prompt_with_none_context_returns_string():
    from query_llm import build_prompt
    prompt = build_prompt("What is a UAP?", context=None)
    assert isinstance(prompt, str)
    assert "UAP" in prompt


def test_build_prompt_with_empty_context_returns_string():
    from query_llm import build_prompt
    prompt = build_prompt("test query", context="")
    assert isinstance(prompt, str)
