#!/usr/bin/env python3
"""Retry only the previously-blocked SIGE municipality manifestation.

The source declares FID as its OID and does not support pagination. Because its
provider count is below maxRecordCount, this residual requests the complete
layer once, then requires exact count closure and unique/non-null OIDs. It does
not reacquire the already-passed shoreline or geographic-reference artifacts.
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://sige.pr.gov/server/rest/services/PuertoRico_Advisory/MapServer/0"
UA = "spiderweb-pr-sige-municipality-residual/1.1 (+https://github.com/jotaele44/spiderweb-pr)"


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha(data: bytes):
    return hashlib.sha256(data).hexdigest()


def get(url: str, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), dict(r.headers.items())


def qurl(**params):
    return BASE + "/query?" + urllib.parse.urlencode(params)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="evidence/pr_archipelago/geometry_snapshots/sige_municipality_residual")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    meta_url = BASE + "?f=pjson"
    meta_b, _ = get(meta_url)
    meta = json.loads(meta_b.decode("utf-8"))
    (out / "metadata.json").write_bytes(meta_b)
    oid_fields = [f["name"] for f in meta.get("fields", []) if f.get("type") == "esriFieldTypeOID"]
    if len(oid_fields) != 1:
        raise RuntimeError(f"expected exactly one OID field, found {oid_fields!r}")
    oid = oid_fields[0]

    count_url = qurl(where="1=1", returnCountOnly="true", f="json")
    count_b, _ = get(count_url)
    (out / "count.json").write_bytes(count_b)
    expected = int(json.loads(count_b.decode("utf-8"))["count"])
    max_record_count = int(meta.get("maxRecordCount") or 1000)
    if expected > max_record_count:
        raise RuntimeError(
            f"source does not support pagination and expected={expected} exceeds maxRecordCount={max_record_count}"
        )

    data_url = qurl(
        where="1=1", outFields="*", returnGeometry="true", outSR="4326",
        f="geojson", orderByFields=f"{oid} ASC",
    )
    data, headers = get(data_url)
    obj = json.loads(data.decode("utf-8"))
    if obj.get("type") != "FeatureCollection" or not isinstance(obj.get("features"), list):
        raise RuntimeError(f"non-FeatureCollection response: {str(obj)[:500]}")
    (out / "full.geojson").write_bytes(data)
    features = obj["features"]

    ids = [f.get("properties", {}).get(oid) for f in features]
    duplicate_ids = len(ids) - len(set(ids))
    null_ids = sum(x is None for x in ids)
    closed = len(features) == expected and duplicate_ids == 0 and null_ids == 0
    manifest = {
        "schema_version": "1.1",
        "generated_utc": now(),
        "source": BASE,
        "oid_field": oid,
        "pagination_supported": False,
        "max_record_count": max_record_count,
        "expected_count": expected,
        "retained_count": len(features),
        "duplicate_oid_count": duplicate_ids,
        "null_oid_count": null_ids,
        "arithmetic_closed": closed,
        "metadata_sha256": sha(meta_b),
        "count_sha256": sha(count_b),
        "data_sha256": sha(data),
        "data_url": data_url,
        "content_type": headers.get("Content-Type"),
        "state": "PASS_BYTES_FROZEN" if closed else "FAIL",
        "certification": "ADMINISTRATIVE_GEOMETRY_SUPPORT_ONLY",
    }
    mp = out / "sige_municipality_residual_manifest.json"
    mp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps({"manifest": str(mp), "sha256": sha(mp.read_bytes()), "state": manifest["state"], "expected": expected, "retained": len(features), "oid_field": oid}, indent=2))
    return 0 if closed else 2


if __name__ == "__main__":
    raise SystemExit(main())
