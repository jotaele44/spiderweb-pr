"""
EarthGPT iOS — Seam chain builder stage.

Chains individual seam pairs into longer corridor segments.

Usage:
    python -m scripts.seam_chain_builder --in outputs/seams.jsonl --out outputs/seam_chains.jsonl
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import read_jsonl, write_jsonl
from earthgpt.seam_chain import build_seam_chains
from earthgpt.log_utils import log


def main() -> None:
    parser = argparse.ArgumentParser(description="Seam chain builder")
    parser.add_argument("--in", dest="input", required=True, help="Seams JSONL")
    parser.add_argument("--out", required=True, help="Output chains JSONL")
    args = parser.parse_args()

    seams = read_jsonl(args.input)
    log(f"Loaded {len(seams)} seams")

    chains = build_seam_chains(seams)
    log(f"Built {len(chains)} seam chains")

    write_jsonl(args.out, chains)
    log(f"Chains written to: {args.out}")


if __name__ == "__main__":
    main()
