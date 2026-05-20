"""
prepare_data.py — Clean and format PRUAP_MASTER_SOCIAL.csv for RAG or fine-tuning.

Usage:
    python prepare_data.py                    # Outputs chunks.jsonl (for RAG)
    python prepare_data.py --finetune         # Outputs finetune.jsonl (for fine-tuning)
    python prepare_data.py --input my.csv     # Use a custom CSV file
"""

import csv
import hashlib
import json
import argparse
import os
from collections import Counter
from typing import Dict, List


MIN_TEXT_LENGTH = 30  # characters; posts shorter than this are skipped

REQUIRED_CSV_COLUMNS = {"id", "title", "subreddit"}


def validate_source(csv_path: str) -> None:
    """Raise ValueError if *csv_path* is missing required columns.

    Parameters
    ----------
    csv_path:
        Path to the PRUAP_MASTER_SOCIAL.csv (or equivalent) file.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    ValueError
        If required columns are absent.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV source not found: {csv_path}")
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or [])
    missing = REQUIRED_CSV_COLUMNS - cols
    if missing:
        raise ValueError(
            f"CSV source missing required columns: {sorted(missing)}. "
            f"Found: {sorted(cols)}"
        )


def deduplicate(rows: List[dict], strategy: str = "id") -> List[dict]:
    """Remove duplicate rows using the specified strategy.

    Parameters
    ----------
    rows:
        List of cleaned row dicts (as returned by ``clean_rows``).
    strategy:
        ``"id"``   — deduplicate by ``id`` field (default).
        ``"hash"`` — deduplicate by SHA-256 of ``title + text`` content.
        ``"both"`` — deduplicate by id first, then content hash.

    Returns
    -------
    List of deduplicated rows (order preserved; first occurrence kept).
    """
    if strategy not in ("id", "hash", "both"):
        raise ValueError(f"Unknown dedup strategy '{strategy}'. Use 'id', 'hash', or 'both'.")

    seen_ids: set = set()
    seen_hashes: set = set()
    out = []
    for row in rows:
        if strategy in ("id", "both"):
            rid = row.get("id", "")
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
        if strategy in ("hash", "both"):
            content = (row.get("title", "") + row.get("text", "")).encode()
            h = hashlib.sha256(content).hexdigest()
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
        out.append(row)
    return out


def export_stats(rows: List[dict]) -> Dict[str, object]:
    """Return per-subreddit document counts and basic token distribution.

    Parameters
    ----------
    rows:
        List of row dicts (as returned by ``clean_rows``).

    Returns
    -------
    dict with keys:
        ``total``          – total row count
        ``by_subreddit``   – {subreddit: count}
        ``avg_tokens``     – mean token count (whitespace split)
        ``min_tokens``     – minimum token count
        ``max_tokens``     – maximum token count
    """
    if not rows:
        return {"total": 0, "by_subreddit": {}, "avg_tokens": 0,
                "min_tokens": 0, "max_tokens": 0}
    by_sub: Counter = Counter(r.get("subreddit", "") for r in rows)
    token_counts = [
        len((r.get("title", "") + " " + r.get("text", "")).split())
        for r in rows
    ]
    return {
        "total":        len(rows),
        "by_subreddit": dict(by_sub.most_common()),
        "avg_tokens":   round(sum(token_counts) / len(token_counts), 1),
        "min_tokens":   min(token_counts),
        "max_tokens":   max(token_counts),
    }


def load_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def clean_rows(rows):
    """Deduplicate by post id and drop posts with no meaningful text."""
    seen = set()
    cleaned = []
    for row in rows:
        post_id = row.get("id", "").strip()
        title = row.get("title", "").strip()
        text = row.get("text", "").strip()
        content = f"{title} {text}".strip()

        if post_id in seen:
            continue
        if len(content) < MIN_TEXT_LENGTH:
            continue

        seen.add(post_id)
        cleaned.append({
            "id": post_id,
            "created": row.get("created", ""),
            "subreddit": row.get("subreddit", ""),
            "keyword": row.get("keyword", ""),
            "title": title,
            "text": text,
            "url": row.get("url", ""),
            "comments": int(row.get("comments", 0) or 0),
            "score": int(row.get("score", 0) or 0),
        })
    return cleaned


def to_chunks(rows, out_path):
    """Write one JSON object per line, suitable for RAG ingestion."""
    with open(out_path, "w", encoding="utf-8") as f:
        for row in rows:
            body = row["title"]
            if row["text"]:
                body += "\n\n" + row["text"]
            chunk = {
                "id": row["id"],
                "text": body,
                "metadata": {
                    "subreddit": row["subreddit"],
                    "keyword": row["keyword"],
                    "url": row["url"],
                    "created": row["created"],
                    "score": row["score"],
                    "comments": row["comments"],
                },
            }
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    print(f"Wrote {len(rows)} chunks to {out_path}")


def to_finetune(rows, out_path):
    """Write instruction-tuning pairs in JSONL format for fine-tuning."""
    with open(out_path, "w", encoding="utf-8") as f:
        for row in rows:
            body = row["title"]
            if row["text"]:
                body += "\n\n" + row["text"]
            pair = {
                "prompt": (
                    f"You are an expert on UAP/UFO phenomena in Puerto Rico. "
                    f"Summarize the following Reddit post from r/{row['subreddit']}:\n\n{body}"
                ),
                "completion": (
                    f"This post discusses: {row['title']}. "
                    f"It was posted on {row['created'][:10]} with {row['comments']} comments "
                    f"and a score of {row['score']}. Source: {row['url']}"
                ),
            }
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")
    print(f"Wrote {len(rows)} fine-tuning pairs to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Prepare PRUAP social data for LLM use.")
    parser.add_argument("--input", default="PRUAP_MASTER_SOCIAL.csv", help="Input CSV file")
    parser.add_argument("--finetune", action="store_true", help="Output fine-tuning pairs instead of RAG chunks")
    parser.add_argument("--out", default=None, help="Output JSONL path (default: chunks.jsonl or finetune.jsonl)")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: '{args.input}' not found. Run merge.py first to produce the master CSV.")
        exit(1)

    rows = load_csv(args.input)
    print(f"Loaded {len(rows)} raw rows from {args.input}")

    rows = clean_rows(rows)
    print(f"After cleaning: {len(rows)} rows kept")

    if args.finetune:
        out = args.out or "finetune.jsonl"
        to_finetune(rows, out)
    else:
        out = args.out or "chunks.jsonl"
        to_chunks(rows, out)


if __name__ == "__main__":
    main()
