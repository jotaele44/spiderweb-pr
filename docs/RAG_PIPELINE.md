# RAG Pipeline

The RAG (Retrieval-Augmented Generation) pipeline processes Puerto Rico UAP/UFO social-media data from `PRUAP_MASTER_SOCIAL.csv`, embeds it into a vector index, and grounds a local open-source LLM with retrieved context at query time.

---

## Setup and requirements

```bash
pip install -r requirements-rag.txt
# Installs: chromadb sentence-transformers transformers torch accelerate
```

**Environment variable**

| Variable | Required | Purpose |
|----------|----------|---------|
| `HF_TOKEN` | Required for gated models | Hugging Face authentication token. Set before running `query_llm.py` with Llama or other access-restricted models. |

```bash
export HF_TOKEN=hf_...
```

Ungated models such as `google/gemma-2-2b-it` and `mistralai/Mistral-7B-Instruct-v0.3` do not require `HF_TOKEN`.

---

## Data flow

```
PRUAP_MASTER_SOCIAL.csv
        │
        ▼
  prepare_data.py        ← deduplication, length filtering, field normalization
        │
        ▼
  chunks.jsonl           ← one JSON object per post: id, text, metadata
        │
        ▼
  rag_pipeline.py        ← embedding (all-MiniLM-L6-v2) + ChromaDB upsert
        │
        ▼
  ./pruap_index/         ← persistent ChromaDB vector index
        │
        ▼
  query_llm.py           ← retrieve top-k → build prompt → generate answer
```

---

## `prepare_data.py`

Cleans and formats `PRUAP_MASTER_SOCIAL.csv` for RAG ingestion or LLM fine-tuning.

**CLI usage**

```bash
python prepare_data.py                        # → chunks.jsonl (RAG mode)
python prepare_data.py --finetune             # → finetune.jsonl (fine-tune mode)
python prepare_data.py --input my.csv         # custom input file
python prepare_data.py --out custom.jsonl     # custom output path
```

### Key functions

#### `load_csv(path) -> list[dict]`

Reads the CSV with UTF-8 encoding and returns all rows as a list of `DictReader` dicts.

#### `clean_rows(rows) -> list[dict]` — deduplicate and validate

Deduplicates by post `id`, drops posts where the combined `title + text` is shorter than 30 characters (`MIN_TEXT_LENGTH`). Returns cleaned rows with fields: `id`, `created`, `subreddit`, `keyword`, `title`, `text`, `url`, `comments` (int), `score` (int).

#### `to_chunks(rows, out_path)` — export for RAG

Writes one JSON object per line to `out_path`. Each chunk has:

```json
{
  "id": "...",
  "text": "<title>\n\n<text>",
  "metadata": {
    "subreddit": "...", "keyword": "...", "url": "...",
    "created": "...", "score": 0, "comments": 0
  }
}
```

#### `to_finetune(rows, out_path)` — export for fine-tuning

Writes instruction-tuning pairs in JSONL format with `prompt` and `completion` fields. The prompt frames the post as a UAP expert summarization task; the completion summarizes date, engagement, and source URL.

### `PrepareData` class methods (planned extension)

The following methods are planned for a future class-based refactor of `prepare_data.py`:

| Method | Description |
|--------|-------------|
| `validate_source(path)` | Checks that the input CSV exists, is UTF-8 decodable, and contains the required columns (`id`, `title`, `text`). |
| `deduplicate(rows)` | Removes duplicate post IDs; returns deduplicated list and a count of dropped rows. |
| `split(rows, train_ratio=0.9)` | Splits cleaned rows into train/validation sets for fine-tuning. |
| `export_stats(out_path)` | Writes a JSON summary of row counts, subreddit distribution, keyword coverage, and date range. |

---

## `rag_pipeline.py`

Embeds chunks from `chunks.jsonl` into a ChromaDB vector collection and retrieves relevant posts by cosine similarity.

**CLI usage**

```bash
python rag_pipeline.py --build                                         # index all chunks
python rag_pipeline.py --query "strange lights over Laguna del Condado"
python rag_pipeline.py --build --chunks my_chunks.jsonl --db ./my_index
python rag_pipeline.py --query "..." --db ./my_index --top-k 10
```

**Defaults**

| Parameter | Default |
|-----------|---------|
| Embedding model | `all-MiniLM-L6-v2` |
| ChromaDB path | `./pruap_index` |
| Collection name | `pruap_social` |
| Similarity metric | cosine |
| Batch size (upsert) | 256 |
| Top-k | 5 |

### Key functions

#### `build_index(chunks_path, db_path)`

Loads all chunks from `chunks_path`, embeds with `SentenceTransformer("all-MiniLM-L6-v2")`, and upserts into a ChromaDB `PersistentClient` in batches of 256. Existing entries are updated (upsert semantics — safe to re-run after adding new data).

#### `retrieve(query, db_path, top_k) -> list[dict]`

Embeds `query` and returns the `top_k` closest documents. Each result is a dict with keys `text`, `metadata`, and `score` (cosine similarity, 0–1).

#### `format_context(hits) -> str`

Formats a list of retrieved hits into an LLM-ready context block with numbered citations, subreddit, date, score, and URL per entry.

### `RAGPipeline` class methods (planned extension)

| Method | Description |
|--------|-------------|
| `incremental_update(chunks_path)` | Upserts only chunks whose `id` is not already in the index, avoiding full re-embedding. |
| `index_stats() -> dict` | Returns collection count, embedding model name, and disk usage of the ChromaDB directory. |
| `benchmark(queries, top_k=5) -> pd.DataFrame` | Runs a list of queries and reports per-query latency and top-1 similarity score. |
| `export_index(out_path)` | Serializes the ChromaDB collection to a portable archive (zip of the persistent directory). |
| `import_index(archive_path)` | Extracts and loads a previously exported index archive into the configured `db_path`. |

---

## `query_llm.py`

RAG-grounded question-answering CLI. Retrieves relevant posts from the vector index and feeds them as context to a local Hugging Face causal LM.

**CLI usage**

```bash
python query_llm.py "What UAP sightings have been reported near Aguadilla?"
python query_llm.py "Are there reports of USOs near Puerto Rico?" --top-k 8
python query_llm.py "..." --model mistralai/Mistral-7B-Instruct-v0.3
python query_llm.py "..." --no-context        # LLM-only, no RAG retrieval
python query_llm.py "..." --db ./my_index     # custom index path
```

**Supported models** (downloaded automatically on first run)

| Model | Size | Notes |
|-------|------|-------|
| `google/gemma-2-2b-it` (default) | ~5 GB | Fast; suitable for laptops |
| `mistralai/Mistral-7B-Instruct-v0.3` | ~14 GB | Higher quality |
| `meta-llama/Llama-3.2-3B-Instruct` | ~6 GB | Requires `HF_TOKEN` |

**Generation defaults**: `max_new_tokens=512`, greedy decoding (`do_sample=False`), prompt tokens excluded from output.

### Key functions

#### `build_prompt(query, context=None) -> str`

Constructs the LLM prompt. With `context`, wraps retrieved posts under `### Relevant Posts` and appends `### Question` / `### Answer` sections. Without context, uses a direct instruction format. The system persona is a Puerto Rico UAP expert researcher.

#### `load_model(model_id) -> (tokenizer, model)`

Loads tokenizer and model via `transformers.AutoModelForCausalLM.from_pretrained`. Reads `HF_TOKEN` from the environment. Uses `torch.float16` on CUDA, `float32` on CPU, with `device_map="auto"` and `low_cpu_mem_usage=True`.

#### `generate(tokenizer, model, prompt) -> str`

Runs `model.generate()` and decodes only the newly generated tokens (prompt tokens excluded).

#### `get_context(query, db_path, top_k) -> str | None`

Calls `rag_pipeline.retrieve()` and `rag_pipeline.format_context()` to produce an LLM-ready context string. Returns `None` if the index does not exist or no results are found.

### `QueryLLM` class methods (planned extension)

| Method | Description |
|--------|-------------|
| `with_citations(query, top_k=5) -> dict` | Returns the generated answer alongside a structured list of source URLs and similarity scores used as context. |
| `batch_query(queries, top_k=5) -> list[dict]` | Processes a list of questions in sequence, returning one result dict per query with `question`, `answer`, and `sources`. |
| `stream(query) -> Generator[str]` | Yields answer tokens as they are generated using `TextStreamer`, suitable for interactive terminals. |
| `set_template(template_str)` | Overrides the default prompt template. Use `{context}` and `{query}` as placeholders. |
| `self_critique(query, top_k=5) -> dict` | Generates an initial answer, then prompts the model to identify unsupported claims, returning both the answer and a critique. |

---

## Brief setup example

```bash
# 1. Install dependencies
pip install chromadb sentence-transformers transformers torch accelerate

# 2. Export HF token (required for gated models)
export HF_TOKEN=hf_...

# 3. Prepare chunks from the master CSV
python prepare_data.py                    # → chunks.jsonl

# 4. Build the vector index
python rag_pipeline.py --build            # → ./pruap_index/

# 5. Query
python query_llm.py "Where have USOs been reported around Puerto Rico?"
```

The first run of `query_llm.py` downloads the model (~5 GB for the default Gemma model). Subsequent runs load from the HuggingFace local cache (`~/.cache/huggingface/`).
