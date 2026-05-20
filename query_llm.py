"""
query_llm.py — Ask questions about Puerto Rico UAP/UFO sightings using a local
open-source LLM grounded with your Reddit data (RAG).

Usage:
    python query_llm.py "What UAP sightings have been reported near Aguadilla?"
    python query_llm.py "Are there reports of USOs near Puerto Rico?" --top-k 8
    python query_llm.py "..." --model mistralai/Mistral-7B-Instruct-v0.3
    python query_llm.py "..." --no-context    # LLM only, no RAG

Requires:
    pip install transformers torch accelerate chromadb sentence-transformers

Models (downloaded automatically on first run):
    - google/gemma-2-2b-it          ~5 GB, fast, good for laptops
    - mistralai/Mistral-7B-Instruct-v0.3   ~14 GB, higher quality
    - meta-llama/Llama-3.2-3B-Instruct     ~6 GB (requires HF token)

Set HF_TOKEN env var if the model requires Hugging Face authentication:
    export HF_TOKEN=hf_...
"""

import argparse
import os
import sys

DEFAULT_MODEL = "google/gemma-2-2b-it"
DEFAULT_TOP_K = 5
DEFAULT_DB = "./pruap_index"
MAX_NEW_TOKENS = 512


def build_prompt(query, context=None):
    if context:
        return (
            "You are an expert researcher on UAP/UFO phenomena in Puerto Rico. "
            "Use the following Reddit posts as your primary source of information. "
            "If the posts do not contain relevant information, say so clearly.\n\n"
            f"### Relevant Posts\n{context}\n\n"
            f"### Question\n{query}\n\n"
            "### Answer"
        )
    return (
        "You are an expert researcher on UAP/UFO phenomena in Puerto Rico. "
        f"Answer the following question to the best of your ability.\n\n"
        f"### Question\n{query}\n\n"
        "### Answer"
    )


def load_model(model_id):
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import torch

    token = os.getenv("HF_TOKEN")
    print(f"Loading model '{model_id}'... (downloads on first run)")

    tokenizer = AutoTokenizer.from_pretrained(model_id, token=token)
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        token=token,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    return tokenizer, model


def generate(tokenizer, model, prompt):
    import torch

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    input_len = inputs["input_ids"].shape[1]

    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            temperature=1.0,
            pad_token_id=tokenizer.eos_token_id,
        )

    # Decode only the newly generated tokens (exclude the prompt)
    new_tokens = output[0][input_len:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def sanitize_query(query: str, max_length: int = 1000) -> str:
    """Strip leading/trailing whitespace and truncate to *max_length* chars.

    Removes ASCII control characters (0x00-0x1F except tab/newline) that could
    confuse downstream tokenizers.
    """
    cleaned = "".join(c for c in query if c == "\t" or c == "\n" or ord(c) >= 0x20)
    return cleaned.strip()[:max_length]


def truncate_context(context: str, max_chars: int = 4000) -> str:
    """Truncate *context* to *max_chars* characters, appending a marker if cut."""
    if not context or len(context) <= max_chars:
        return context
    return context[:max_chars] + "\n... [context truncated]"


def estimate_tokens(text: str) -> int:
    """Rough token-count estimate: ~4 characters per token (BPE heuristic).

    Returns an integer ≥ 0. This is intentionally approximate — use only for
    guard-rail checks, not billing or exact context-window management.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def get_context(query, db_path, top_k):
    """Retrieve RAG context from the vector index."""
    try:
        from rag_pipeline import retrieve, format_context
    except ImportError:
        print("Error: rag_pipeline.py not found. Make sure it is in the same directory.")
        sys.exit(1)

    if not os.path.exists(db_path):
        print(
            f"Warning: Vector index not found at '{db_path}'.\n"
            "Run the following to build it first:\n"
            "  python prepare_data.py\n"
            "  python rag_pipeline.py --build\n"
        )
        return None

    hits = retrieve(query, db_path, top_k)
    if not hits:
        return None
    return format_context(hits)


def main():
    parser = argparse.ArgumentParser(description="Query your PRUAP data with a local LLM.")
    parser.add_argument("query", help="Your question about UAP/UFO sightings in Puerto Rico")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Hugging Face model ID")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Number of RAG results to use")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to ChromaDB index")
    parser.add_argument("--no-context", action="store_true", help="Skip RAG; use LLM knowledge only")
    args = parser.parse_args()

    context = None
    if not args.no_context:
        print("Retrieving relevant posts...")
        context = get_context(args.query, args.db, args.top_k)
        if context:
            print(f"Found context from {args.top_k} posts.\n")
        else:
            print("No relevant posts found; answering without context.\n")

    prompt = build_prompt(args.query, context)

    tokenizer, model = load_model(args.model)

    print(f"\nQuestion: {args.query}\n")
    print("Generating answer...\n")
    answer = generate(tokenizer, model, prompt)

    print("=" * 60)
    print(answer)
    print("=" * 60)

    if context:
        print("\nSources used:")
        for line in context.split("\n"):
            if line.startswith("[") or "reddit.com" in line:
                print(" ", line)


if __name__ == "__main__":
    main()
