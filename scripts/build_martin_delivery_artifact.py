from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DELIVERY = ROOT / "configs" / "martin_delivery.yaml"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build(source_id: str, source_path: Path, output_path: Path, receipt_path: Path | None = None) -> dict:
    registry = yaml.safe_load(DELIVERY.read_text(encoding="utf-8")) or {}
    source = registry["sources"][source_id]
    canonical_sha = _sha(source_path)
    if canonical_sha != source["expected_artifact_sha256"]:
        raise ValueError(f"canonical hash drift: {canonical_sha}")

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    features = payload.get("features", [])
    if len(features) != source["expected_feature_count"]:
        raise ValueError(f"feature-count drift: {len(features)}")

    identity = source["expected_identity_field"]
    allowed = list(source["delivery_properties"]["include"])
    if identity not in allowed:
        raise ValueError("identity field must be public in delivery derivative")

    source_ids: list[str] = []
    output_features: list[dict] = []
    for feature in features:
        props = feature.get("properties") or {}
        geoid = str(props.get(identity, ""))
        if not geoid:
            raise ValueError("empty identity")
        source_ids.append(geoid)
        output_features.append({
            "type": "Feature",
            "geometry": feature.get("geometry"),
            "properties": {key: props.get(key) for key in allowed},
        })

    if len(source_ids) != len(set(source_ids)):
        raise ValueError("duplicate identity")

    out = {"type": "FeatureCollection", "features": output_features}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    roundtrip = json.loads(output_path.read_text(encoding="utf-8"))
    delivered_ids = {str(f["properties"][identity]) for f in roundtrip["features"]}
    source_set = set(source_ids)
    unexpected = sorted({k for f in roundtrip["features"] for k in f.get("properties", {})} - set(allowed))
    if source_set != delivered_ids or unexpected:
        raise AssertionError("delivery identity/property parity failed")

    receipt = {
        "source_id": source_id,
        "canonical_sha256": canonical_sha,
        "delivery_sha256": _sha(output_path),
        "feature_count": len(features),
        "identity_count": len(source_set),
        "source_only": sorted(source_set - delivered_ids),
        "delivery_only": sorted(delivered_ids - source_set),
        "symmetric_difference_count": len(source_set ^ delivered_ids),
        "public_properties": allowed,
        "unexpected_properties": unexpected,
    }
    if receipt_path:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-id", default="municipios")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    build(args.source_id, args.source, args.output, args.receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
