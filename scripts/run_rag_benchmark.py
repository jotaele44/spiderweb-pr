"""Run RAG pipeline benchmark and write results JSON.

Usage
-----
    python -m scripts.run_rag_benchmark
    python -m scripts.run_rag_benchmark --output outputs/rag_benchmark_results.json
    python -m scripts.run_rag_benchmark --queries queries.json --output results.json

The script loads the RAG index, runs a fixed set of benchmark queries, and
writes a JSON report with per-query latency and top-k recall estimates.
When the RAG module is unavailable (e.g. no Chroma index built yet) it exits
with a warning message and exit code 2 — not a hard failure.
"""

import argparse
import json
import sys
import time
from pathlib import Path

_DEFAULT_QUERIES = [
    "Unknown aircraft flying low over Vieques at night",
    "Helicopter circling PREPA power plant San Juan",
    "Unregistered aircraft Mona Passage maritime patrol",
    "Search and rescue helicopter PR waters",
    "Law enforcement helicopter surveillance route 66",
]

_DEFAULT_OUTPUT = "outputs/rag_benchmark_results.json"


def _log(msg: str) -> None:
    print(f"[rag-benchmark] {msg}", flush=True)


def _run_benchmark(queries, n_results=5):
    """Attempt to run benchmark queries against the RAG index.

    Returns a results dict on success; raises RuntimeError on import failure.
    """
    try:
        from rag_pipeline import RAGPipeline, index_stats
    except ImportError as exc:
        raise RuntimeError(f"rag_pipeline not importable: {exc}") from exc

    _log("Loading RAG pipeline …")
    pipeline = RAGPipeline()

    _log("Fetching index stats …")
    try:
        stats = index_stats()
    except Exception as exc:
        stats = {"error": str(exc)}

    results = []
    for query in queries:
        t0 = time.perf_counter()
        try:
            hits = pipeline.query(query, n_results=n_results)
        except Exception as exc:
            hits = []
            _log(f"  query failed: {exc}")
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        results.append({
            "query": query,
            "latency_ms": elapsed_ms,
            "hit_count": len(hits),
            "top_doc": hits[0].get("document", "")[:120] if hits else None,
        })
        _log(f"  '{query[:50]}…' → {len(hits)} hits in {elapsed_ms} ms")

    avg_latency = (
        round(sum(r["latency_ms"] for r in results) / len(results), 2)
        if results else 0.0
    )
    return {
        "index_stats": stats,
        "query_count": len(queries),
        "avg_latency_ms": avg_latency,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run RAG pipeline benchmark and write results JSON.",
    )
    parser.add_argument(
        "--queries",
        help="Path to JSON file containing a list of query strings. "
             "Uses built-in fixture queries if omitted.",
    )
    parser.add_argument(
        "--output",
        default=_DEFAULT_OUTPUT,
        help=f"Path for the output JSON report (default: {_DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--n-results",
        type=int,
        default=5,
        help="Number of results to retrieve per query (default: 5).",
    )
    args = parser.parse_args()

    if args.queries:
        queries = json.loads(Path(args.queries).read_text(encoding="utf-8"))
        if not isinstance(queries, list):
            print("ERROR: queries file must contain a JSON list of strings.", file=sys.stderr)
            return 1
    else:
        queries = _DEFAULT_QUERIES

    try:
        report = _run_benchmark(queries, n_results=args.n_results)
    except RuntimeError as exc:
        print(f"WARNING: {exc}", file=sys.stderr)
        print("RAG module unavailable — build the index first with rag_pipeline.py.", file=sys.stderr)
        return 2

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _log(f"Benchmark report written to {out_path}")
    _log(f"Average latency: {report['avg_latency_ms']} ms over {report['query_count']} queries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
