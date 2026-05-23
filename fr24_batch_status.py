"""
FR24 BATCH STATUS

Summarizes the FR24 OCR batch ledger by batch_id and mode.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import List


def read_csv(path: Path) -> List[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return list(csv.DictReader(path.open(encoding="utf-8")))


def summarize_ledger(ledger: Path) -> dict:
    rows = read_csv(ledger)
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row.get("batch_id", ""), row.get("mode", ""))].append(row)

    groups = []
    for (batch_id, mode), items in sorted(grouped.items()):
        groups.append({
            "batch_id": batch_id,
            "mode": mode,
            "records": len(items),
            "status_counts": dict(Counter(i.get("status", "") for i in items)),
            "unique_images": len({i.get("image_path", "") for i in items if i.get("image_path")}),
        })

    summary = {
        "ledger": str(ledger),
        "records": len(rows),
        "groups": groups,
        "overall_status_counts": dict(Counter(r.get("status", "") for r in rows)),
        "policy": "candidate_only_no_auto_confirmation",
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize FR24 OCR batch ledger")
    parser.add_argument("--ledger", default="data/_manifests/fr24_audit/fr24_batch_run_ledger.csv")
    args = parser.parse_args()
    print(json.dumps(summarize_ledger(Path(args.ledger)), indent=2))


if __name__ == "__main__":
    main()
