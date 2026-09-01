from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DELIVERY_PATH = ROOT / "configs" / "martin_delivery.yaml"
CATALOG_PATH = ROOT / "configs" / "layer_catalog.yaml"

BASE_CONFIG = {
    "listen_addresses": "0.0.0.0:3000",
    "keep_alive": 75,
    "worker_processes": 2,
    "cache": {"size_mb": 64, "minzoom": 0, "maxzoom": 14},
    "cors": {
        "origin": ["http://localhost:5173", "http://127.0.0.1:5173"],
        "max_age": 3600,
    },
    "observability": {"metrics": {}},
    "geojson": {"extent": 4096, "buffer": 64, "sources": {}},
}


def _bytes(path: Path) -> bytes:
    return path.read_bytes()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _catalog_visibility() -> dict[str, str]:
    catalog = _load_yaml(CATALOG_PATH)
    out: dict[str, str] = {}
    for family in catalog.get("families", []):
        visibility = family.get("visibility")
        for layer in family.get("layers", []):
            out[layer["layer_id"]] = visibility
    return out


def compile_config(environment: str) -> tuple[str, dict]:
    delivery = _load_yaml(DELIVERY_PATH)
    policy = delivery.get("state_machine", {}).get("runtime_authorization", {})
    allowed = set(policy.get(environment, []))
    if not allowed:
        raise ValueError(f"unknown or empty environment policy: {environment}")

    visibility = _catalog_visibility()
    config = json.loads(json.dumps(BASE_CONFIG))
    admitted: list[str] = []

    for source_id, source in sorted(delivery.get("sources", {}).items()):
        state = source.get("publication_state")
        if state in set(delivery.get("state_machine", {}).get("never_serve", [])):
            continue
        if state not in allowed:
            continue
        layer = source.get("source_layer")
        required_visibility = source.get("visibility_required")
        if visibility.get(layer) != required_visibility or required_visibility != "V3":
            raise ValueError(f"{source_id}: runtime publication requires canonical V3 visibility")
        if not source.get("certification_receipt"):
            raise ValueError(f"{source_id}: certification receipt missing")
        props = source.get("delivery_properties") or {}
        if props.get("exclude_by_default") is not True or not props.get("include"):
            raise ValueError(f"{source_id}: explicit property whitelist required")
        if source.get("source_type") != "geojson":
            raise ValueError(f"{source_id}: unsupported source_type for current compiler")
        config["geojson"]["sources"][source["martin_source_id"]] = source["martin_artifact_path"]
        admitted.append(source_id)

    if "paths" in config["geojson"]:
        raise AssertionError("geojson.paths is forbidden")

    rendered = yaml.safe_dump(config, sort_keys=True, allow_unicode=True)
    manifest = {
        "environment": environment,
        "admitted_sources": admitted,
        "input_sha256": {
            "configs/martin_delivery.yaml": _sha(_bytes(DELIVERY_PATH)),
            "configs/layer_catalog.yaml": _sha(_bytes(CATALOG_PATH)),
        },
        "config_sha256": _sha(rendered.encode("utf-8")),
    }
    return rendered, manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=["canary", "certification", "production"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    rendered, manifest = compile_config(args.environment)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    manifest_path = args.manifest or args.output.with_suffix(args.output.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
