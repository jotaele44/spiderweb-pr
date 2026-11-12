"""Do not interpret user RAG questions as command-line options."""
import pytest
from pydantic import ValidationError

from server.backend.main import RagQueryRequest, _rag_query_command


def test_query_option_prefix_stays_positional():
    cmd = _rag_query_command("--model=attacker/model", 5, False)
    assert cmd[-2:] == ["--", "--model=attacker/model"]
    assert cmd[:2][1].endswith("query_llm.py")
    assert "--top-k" in cmd


def test_query_with_spaces_remains_single_argument():
    cmd = _rag_query_command("find --db secret", 4, True)
    assert cmd[-1] == "find --db secret"
    assert cmd[-2] == "--"
    assert "--no-context" in cmd


@pytest.mark.parametrize("bad", ["", "x" * 1001])
def test_rejects_unbounded_query(bad):
    with pytest.raises(ValidationError):
        RagQueryRequest(query=bad)


@pytest.mark.parametrize("bad", [0, -1, 21, 1000000])
def test_rejects_unbounded_top_k(bad):
    with pytest.raises(ValidationError):
        _rag_query_command("question", bad, False)
