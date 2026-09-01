#!/usr/bin/env python3
"""Compatibility entrypoint for the Spiderweb RAG backend.

The FastAPI orchestration layer invokes ``ROOT/query_llm.py``. The canonical
implementation lives under ``llm/query_llm.py``; keep this wrapper intentionally
thin so the backend path resolves without duplicating query logic.
"""

from llm.query_llm import main


if __name__ == "__main__":
    main()
