"""
prepare_data.py — Clean and format PRUAP_MASTER_SOCIAL.csv for RAG or fine-tuning.

Usage:
    python prepare_data.py                    # Outputs chunks.jsonl (for RAG)
    python prepare_data.py --finetune         # Outputs finetune.jsonl (for fine-tuning)
    python prepare_data.py --input my.csv     # Use a custom CSV file
"""

import csv
import json
import argparse
import os


MIN_TEXT_LENGTH = 30  # characters; posts shorter than this are skipped


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
