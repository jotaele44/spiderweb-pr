"""
EarthGPT iOS — Cluster builder.

Clusters propagated anomaly nodes into candidate groups.

Usage:
    python -m scripts.build_clusters --prop outputs/propagated_tiles.jsonl --out outputs/clusters.jsonl
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import read_jsonl, write_jsonl
from earthgpt.corridor_graph import build_corridor_candidates
from earthgpt.log_utils import log, warn


def main() -> None:
    parser = argparse.ArgumentParser(description="Cluster builder from propagated tiles")
    parser.add_argument("--prop", required=True, help="Propagated tiles JSONL")
    parser.add_argument("--out", required=True, help="Output clusters JSONL")
    parser.add_argument("--min_tiles", type=int, default=2)
    parser.add_argument("--max_gap", type=float, default=0.02)
    parser.add_argument("--min_score", type=float, default=0.2)
    args = parser.parse_args()

    nodes = read_jsonl(args.prop)
    nodes = [n for n in nodes if float(n.get("score", 0.0)) >= args.min_score]
    log(f"Clusterable nodes (score >= {args.min_score}): {len(nodes)}")

    if not nodes:
        warn("No nodes to cluster — writing empty output.")
        write_jsonl(args.out, [])
        return

    clusters = build_corridor_candidates(
        nodes, seams=[], max_gap_deg=args.max_gap, min_tiles=args.min_tiles
    )
    log(f"Clusters built: {len(clusters)}")
    write_jsonl(args.out, clusters)
    log(f"Clusters written to: {args.out}")


if __name__ == "__main__":
    main()
