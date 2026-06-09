# llm

LLM query + retrieval layer over the flight-intelligence database.

## What's here
- `query_llm.py` — the query entry point.
- `rag_pipeline.py` — retrieval-augmented generation pipeline.
- `prepare_data.py` — corpus preparation for retrieval.

## Install
The RAG stack is heavy (torch, transformers, chromadb, sentence-transformers)
and is **excluded from CI** for that reason. Install locally with:

```bash
pip install -e ".[rag]"
```

## Tests
`tests/test_query_llm.py` and `tests/test_rag_pipeline.py` exercise this layer
with the heavy deps stubbed where possible so they run in the base suite.
