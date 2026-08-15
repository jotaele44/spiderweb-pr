#!/usr/bin/env python3
"""Runtime MVT/identity/failure controls for the municipios Martin canary."""
from __future__ import annotations

import argparse
import json
import math
import urllib.error
import urllib.request
from pathlib import Path

import mapbox_vector_tile
import yaml

ROOT = Path(__file__).resolve().parent.parent
DELIVERY = ROOT / "configs" / "martin_delivery.yaml"


def request(url: str, *, headers: dict[str, str] | None = None):
    req = urllib.request.Request(url, headers=headers or {})
    return urllib.request.urlopen(req, timeout=15)


def lon2x(lon: float, z: int) -> int:
    return int((lon + 180.0) / 360.0 * (1 << z))


def lat2y(lat: float, z: int) -> int:
    lat_r = math.radians(lat)
    return int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * (1 << z))


def source_geoids(path: Path, field: str) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(f["properties"][field]) for f in payload["features"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:3000")
    parser.add_argument("--source", default="/spiderweb-data/municipios.geojson")
    parser.add_argument("--zoom", type=int, default=10)
    args = parser.parse_args()
    base = args.base.rstrip("/")

    delivery = yaml.safe_load(DELIVERY.read_text(encoding="utf-8"))
    spec = delivery["sources"]["municipios"]
    field = spec["expected_identity_field"]
    expected = source_geoids(Path(args.source), field)
    if len(expected) != spec["expected_feature_count"]:
        raise RuntimeError(f"source ID count {len(expected)} != {spec['expected_feature_count']}")
    if any(not geoid.startswith(spec["expected_state_fips_prefix"]) for geoid in expected):
        raise RuntimeError("source contains non-PR GEOID")

    # Health must be independently reachable.
    with request(f"{base}/health") as response:
        if response.status != 200:
            raise RuntimeError(f"health returned {response.status}")

    # Enumerate the PR bounding box at a fixed zoom and reconstruct logical IDs
    # from all MVT manifestations. Duplicate appearances across clipped tiles are
    # expected and collapsed into this set.
    west, south, east, north = -68.0, 17.0, -65.0, 19.0
    z = args.zoom
    xs = range(lon2x(west, z), lon2x(east, z) + 1)
    ys = range(lat2y(north, z), lat2y(south, z) + 1)
    observed: set[str] = set()
    nonempty_url: str | None = None
    nonempty_etag: str | None = None

    for x in xs:
        for y in ys:
            url = f"{base}/municipios/{z}/{x}/{y}"
            try:
                with request(url, headers={"Accept": "application/vnd.mapbox-vector-tile"}) as response:
                    data = response.read()
                    if response.status != 200 or not data:
                        continue
                    ctype = response.headers.get("content-type", "").lower()
                    if not any(token in ctype for token in ("mapbox-vector-tile", "protobuf", "octet-stream")):
                        raise RuntimeError(f"unexpected MVT content-type {ctype!r}")
                    decoded = mapbox_vector_tile.decode(data)
                    layer = decoded.get(spec["source_layer"])
                    if not layer:
                        continue
                    features = layer.get("features", [])
                    if features and nonempty_url is None:
                        nonempty_url = url
                        nonempty_etag = response.headers.get("etag")
                    for feature in features:
                        value = feature.get("properties", {}).get(field)
                        if value is not None:
                            observed.add(str(value))
            except urllib.error.HTTPError as exc:
                if exc.code not in (204, 404):
                    raise

    source_only = sorted(expected - observed)
    mvt_only = sorted(observed - expected)
    if source_only or mvt_only:
        raise RuntimeError(
            f"GEOID parity failed source_only={source_only[:10]} mvt_only={mvt_only[:10]}"
        )
    if len(observed) != spec["expected_feature_count"]:
        raise RuntimeError(f"MVT logical ID count {len(observed)} != {spec['expected_feature_count']}")
    if nonempty_url is None:
        raise RuntimeError("no non-empty municipios tile found")

    # Cache contract: a non-empty tile must advertise ETag and honor If-None-Match.
    if not nonempty_etag:
        raise RuntimeError("non-empty MVT tile missing ETag")
    try:
        request(nonempty_url, headers={"If-None-Match": nonempty_etag}).close()
        raise RuntimeError("If-None-Match did not return 304")
    except urllib.error.HTTPError as exc:
        if exc.code != 304:
            raise RuntimeError(f"If-None-Match returned {exc.code}, expected 304") from exc

    # A remote tile cannot leak PR features.
    remote = f"{base}/municipios/8/0/0"
    try:
        with request(remote) as response:
            remote_data = response.read()
            if remote_data:
                decoded = mapbox_vector_tile.decode(remote_data)
                layer = decoded.get(spec["source_layer"])
                if layer and layer.get("features"):
                    raise RuntimeError("outside-PR tile unexpectedly contains municipios features")
    except urllib.error.HTTPError as exc:
        if exc.code not in (204, 404):
            raise

    # Invalid zoom must fail rather than silently aliasing valid data.
    try:
        request(f"{base}/municipios/99/0/0").close()
        raise RuntimeError("invalid zoom unexpectedly succeeded")
    except urllib.error.HTTPError as exc:
        if exc.code < 400:
            raise RuntimeError(f"invalid zoom returned {exc.code}") from exc

    print(f"PASS: MVT GEOID parity count={len(observed)} symmetric_difference=0")
    print(f"PASS: ETag/304 tile={nonempty_url}")
    print("PASS: outside-PR and invalid-zoom negative controls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
