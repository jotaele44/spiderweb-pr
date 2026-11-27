"""Lossless documentary USGS snapshot export; never a production activation."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import re
import urllib.parse
from datetime import datetime
from pathlib import Path


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _id(prefix, *parts):
    # JSON preserves integer/string source-key distinctions and explicit boundaries.
    raw = json.dumps(
        parts, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()
    return prefix + "_" + _hash(raw)[:32]


def _time(value):
    if (
        not isinstance(value, str)
        or datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None
    ):
        raise ValueError("Snapshot retrieval timestamp requires an explicit timezone")
    return value


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON field")
        value[key] = item
    return value


def _float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite JSON number")
    return result


def build_native_streams(input_manifest, source_root, *, mode="test"):
    """Return canonical-shaped diagnostic streams with exact native features."""
    if mode != "test":
        raise ValueError(
            "Production export BLOCKED: source semantics and consumer gates remain OPEN"
        )
    spec = json.loads(Path(input_manifest).read_text(encoding="utf-8"))
    if (
        spec.get("contract") != "prii.usgs-native-producer-input/v1"
        or spec.get("producer") != "spiderweb-pr"
        or spec.get("mode") != "test"
        or spec.get("activation_state") != "BLOCKED"
        or not spec.get("open_gates")
    ):
        raise ValueError("Expected blocked Spiderweb source-native test input")
    root = Path(source_root).resolve()
    assets = spec.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("No declared input assets")
    sources, observations, coverage = [], [], []
    asset_ids, observation_ids = set(), set()
    for asset in assets:
        aid = asset["asset_id"]
        sid = asset["source_item_id"]
        if (
            not re.fullmatch(r"[0-9a-f]{24}:[0-9]+", aid)
            or aid in asset_ids
            or aid.rsplit(":", 1)[0] != sid
        ):
            raise ValueError("Duplicate asset or source-item identity mismatch")
        asset_ids.add(aid)
        path = (root / asset["raw_file"]).resolve()
        path.relative_to(root)
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Packed input capacity exceeded")
        packed = path.read_bytes()
        if _hash(packed) != asset["packed_sha256"]:
            raise ValueError("Packed input checksum disagreement")
        with gzip.GzipFile(fileobj=io.BytesIO(packed)) as source:
            raw = source.read(5 * 1024 * 1024 + 1)
        if len(raw) > 5 * 1024 * 1024:
            raise ValueError("Expanded input capacity exceeded")
        descriptor = asset["source_descriptor_raw"]
        url = urllib.parse.urlsplit(descriptor.get("downloadUri", ""))
        if (
            url.scheme != "https"
            or url.netloc != "www.sciencebase.gov"
            or url.path != "/catalog/file/get/" + sid
            or url.fragment
        ):
            raise ValueError("Descriptor URL/source-item binding mismatch")
        checksum = descriptor.get("checksum") or {}
        algorithm = str(checksum.get("type", "")).lower().replace("-", "")
        if algorithm not in ("md5", "sha1", "sha256", "sha512"):
            raise ValueError("Unsupported or missing source checksum")
        if (
            len(raw) != descriptor.get("size")
            or _hash(raw) != asset["raw_sha256"]
            or hashlib.new(algorithm, raw).hexdigest() != checksum.get("value")
        ):
            raise ValueError("Raw/source checksum disagreement")
        native = json.loads(
            raw,
            object_pairs_hook=_object,
            parse_float=_float,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError("Non-finite JSON number")
            ),
        )
        features = native.get("features")
        if native.get("type") != "FeatureCollection" or not isinstance(features, list):
            raise ValueError("Expected source-native FeatureCollection")
        if len(features) != asset["expected_features"]:
            raise ValueError("Source feature denominator mismatch")
        when = _time(asset["retrieval_utc"])
        source_id = _id("src", "spiderweb-pr", aid, asset["raw_sha256"])
        inputs = [
            f"sciencebase:{sid}",
            f"asset:{aid}",
            "sha256:" + asset["raw_sha256"],
            "inventory:sha256:" + spec["source_inventory_sha256"],
        ]
        lineage = {
            "producer_script": "scripts/export_usgs_native.py",
            "producer_phase": "USGS_NATIVE_REFERENCE_TEST_ONLY",
            "source_inputs": inputs,
            "extraction_method": (
                "Lossless source snapshot; no geological-even"
                "t time, PR coverage or geometry certification"
            ),
        }
        sources.append(
            {
                "source_id": source_id,
                "source_type": "usgs_source_snapshot",
                "source_name": descriptor.get("name"),
                "source_ref": descriptor.get("downloadUri"),
                "confidence": 0.0,
                "lineage": lineage,
                "synthetic": False,
                "created_at": when,
                "extracted_at": when,
            }
        )
        keys = set()
        for feature in features:
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise ValueError("Malformed native feature")
            key = (feature.get("properties") or {}).get(asset["source_key"])
            if not isinstance(key, (int, str)) or isinstance(key, bool) or key == "":
                raise ValueError("Missing source primary key")
            typed = json.dumps(
                [type(key).__name__, key], ensure_ascii=False, allow_nan=False
            )
            if typed in keys:
                raise ValueError("Duplicate source primary key")
            keys.add(typed)
            oid = _id(
                "obs", "spiderweb-pr", aid, asset["raw_sha256"], type(key).__name__, key
            )
            if oid in observation_ids:
                raise ValueError("Observation identity collision")
            observation_ids.add(oid)
            observations.append(
                {
                    "observation_id": oid,
                    "source_id": source_id,
                    "observation_type": "usgs_feature_source_snapshot",
                    "observed_at": when,
                    "confidence": 0.0,
                    "lineage": lineage,
                    "synthetic": False,
                    "created_at": when,
                    "extracted_at": when,
                    "attributes": {
                        "asset_id": aid,
                        "root_release_ids": asset["root_release_ids"],
                        "source_key_field": asset["source_key"],
                        "source_key_raw": key,
                        "native_feature": feature,
                        "native_collection_metadata": {
                            k: v for k, v in native.items() if k != "features"
                        },
                        "timestamp_semantics": (
                            "SOURCE_RETRIEVAL_ONLY_NOT_GEOLOGICAL_EVENT"
                        ),
                        "confidence_semantics": (
                            "UNASSESSED_DOMAIN_CONFIDENCE_NOT_BYTE_VERIFICATION"
                        ),
                        "spatial_state": "UNRESOLVED",
                        "semantic_state": "OPEN",
                        "activation_state": "BLOCKED",
                        "production_export_state": "BLOCKED",
                    },
                }
            )
        coverage.append(
            {
                "asset_id": aid,
                "features_in": len(features),
                "features_out": len(keys),
                "raw_sha256": asset["raw_sha256"],
                "raw_geometry_transformed": False,
                "canonical_locations_emitted": 0,
            }
        )
    return {
        "sources": sources,
        "observations": observations,
        "entities": [],
        "relationships": [],
    }, {
        "contract": "prii.usgs-native-export-audit/v1",
        "state": "PASS",
        "scope": (
            "TEST-MODE documentary export shape and"
            " exact native feature conservation only"
        ),
        "input_manifest_sha256": _hash(Path(input_manifest).read_bytes()),
        "asset_count": len(assets),
        "source_count": len(sources),
        "feature_count": len(observations),
        "coverage": coverage,
        "open_gates": spec["open_gates"],
        "activation_state": "BLOCKED",
        "production_export_state": "BLOCKED",
        "activated": 0,
    }
