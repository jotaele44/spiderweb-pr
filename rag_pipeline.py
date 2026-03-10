"""
rag_pipeline.py — Build and query a RAG (Retrieval-Augmented Generation) index
over PRUAP social data.

Usage:
    # Step 1: Build the vector index from chunks.jsonl
    python rag_pipeline.py --build

    # Step 2: Retrieve relevant posts for a query
    python rag_pipeline.py --query "strange lights over Laguna del Condado"

    # Optional: specify custom paths
    python rag_pipeline.py --build --chunks my_chunks.jsonl --db ./my_index
    python rag_pipeline.py --query "..." --db ./my_index --top-k 5

Requires:
    pip install chromadb sentence-transformers
"""

import argparse
import json
import os

EMBED_MODEL = "all-MiniLM-L6-v2"   # fast, lightweight, good quality
DEFAULT_DB = "./pruap_index"
DEFAULT_CHUNKS = "chunks.jsonl"
COLLECTION_NAME = "pruap_social"
DEFAULT_TOP_K = 5


def get_collection(db_path):
    import chromadb
    client = chromadb.PersistentClient(path=db_path)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def build_index(chunks_path, db_path):
    """Embed all chunks and store them in a ChromaDB collection."""
    from sentence_transformers import SentenceTransformer

    if not os.path.exists(chunks_path):
        print(f"Error: '{chunks_path}' not found. Run prepare_data.py first.")
        exit(1)

    print(f"Loading chunks from {chunks_path}...")
    with open(chunks_path, encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]
    print(f"  {len(chunks)} chunks loaded")

    print(f"Loading embedding model '{EMBED_MODEL}'...")
    model = SentenceTransformer(EMBED_MODEL)

    collection = get_collection(db_path)

    # Upsert in batches of 256
    batch_size = 256
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c["text"] for c in batch]
        ids = [c["id"] for c in batch]
        metadatas = [c["metadata"] for c in batch]

        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        print(f"  Upserted {min(i + batch_size, len(chunks))}/{len(chunks)} chunks", end="\r")

    print(f"\nIndex built at '{db_path}' with {collection.count()} entries.")


def retrieve(query, db_path, top_k):
    """Embed query and return the top-k most relevant posts."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBED_MODEL)
    query_embedding = model.encode([query]).tolist()

    collection = get_collection(db_path)
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append({"text": doc, "metadata": meta, "score": round(1 - dist, 4)})
    return hits


def format_context(hits):
    """Format retrieved posts into an LLM-ready context string."""
    lines = []
    for i, hit in enumerate(hits, 1):
        meta = hit["metadata"]
        lines.append(
            f"[{i}] r/{meta.get('subreddit', '?')} | {meta.get('created', '')[:10]} | "
            f"score={meta.get('score', '?')} | {meta.get('url', '')}\n"
            f"{hit['text']}\n"
        )
    return "\n---\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="RAG pipeline for PRUAP social data.")
    parser.add_argument("--build", action="store_true", help="Build the vector index")
    parser.add_argument("--query", type=str, help="Query to retrieve relevant posts for")
    parser.add_argument("--chunks", default=DEFAULT_CHUNKS, help="Path to chunks.jsonl")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to ChromaDB persistent directory")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Number of results to return")
    args = parser.parse_args()

    if not args.build and not args.query:
        parser.print_help()
        exit(0)

    if args.build:
        build_index(args.chunks, args.db)

    if args.query:
        print(f"\nQuery: {args.query}\n")
        hits = retrieve(args.query, args.db, args.top_k)
        print(f"Top {len(hits)} results:\n")
        for i, hit in enumerate(hits, 1):
            meta = hit["metadata"]
            print(
                f"[{i}] Similarity: {hit['score']} | r/{meta.get('subreddit','?')} | "
                f"{meta.get('created','')[:10]}"
            )
            print(f"     {meta.get('url', '')}")
            preview = hit["text"][:200].replace("\n", " ")
            print(f"     {preview}...\n")


if __name__ == "__main__":
    main()
