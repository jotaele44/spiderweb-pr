from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "configs" / "martin_delivery.yaml"


def check(source_id: str, target: str) -> dict:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    source = registry["sources"][source_id]
    current = source["publication_state"]
    allowed = set(registry["state_machine"]["allowed_transitions"].get(current, []))
    if target not in allowed:
        raise ValueError(f"invalid transition {current}->{target}")
    if target == "published":
        if current != "validated":
            raise ValueError("publication requires validated source")
        if source.get("visibility_required") != "V3":
            raise ValueError("publication requires V3 visibility")
        if not source.get("certification_receipt"):
            raise ValueError("publication requires certification receipt")
        props = source.get("delivery_properties") or {}
        if props.get("exclude_by_default") is not True or not props.get("include"):
            raise ValueError("publication requires explicit property whitelist")
    receipt = {
        "source_id": source_id,
        "current_state": current,
        "target_state": target,
        "result": "ELIGIBLE_FOR_EXPLICIT_TRANSITION",
        "mutation_performed": False,
        "certification_receipt": source.get("certification_receipt"),
        "canonical_sha256": source.get("expected_artifact_sha256"),
        "feature_count": source.get("expected_feature_count"),
        "identity_field": source.get("expected_identity_field"),
        "public_properties": (source.get("delivery_properties") or {}).get("include", []),
    }
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    receipt = check(args.source, args.target)
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
