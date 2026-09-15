#!/usr/bin/env python3
"""Seed the source-manifestation registry from authoritative provider bytes.

A *manifestation* is one concrete provider object (a specific GeoTIFF, feature
service query, or archive member) that can satisfy a capability over some
footprint. Manifestations are normalised globally rather than copied per cell,
so a 100-cell area of interest resolves to the handful of distinct files that
actually cover it instead of hundreds of duplicate rows.

Footprints are read from each object's own header via an HTTP Range request:
the georeferencing tags of a USGS 1 m GeoTIFF live in the first few kilobytes,
so a ~400 MB tile costs 128 KB to bind. Footprints are therefore provider-
asserted evidence, not guesses derived from the filename.

Byte-level acquisition remains ``tools/spatial_aoi_fetcher``'s job; this module
only establishes what exists and where it sits.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import urllib.parse
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Sequence

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "registry/spatial/source_manifestations.json"

TNM_PRODUCTS_URL = "https://tnmaccess.nationalmap.gov/api/v1/products"
HEADER_BYTES = 131_072
USER_AGENT = "spiderweb-pr/0.1 source-manifestation-seed"

# GeoTIFF tag numbers used for georeferencing.
TAG_IMAGE_WIDTH = 256
TAG_IMAGE_LENGTH = 257
TAG_MODEL_PIXEL_SCALE = 33550
TAG_MODEL_TIEPOINT = 33922
TAG_GEO_KEY_DIRECTORY = 34735
GEO_KEY_PROJECTED_CRS = 3072

_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 12: 8, 16: 8}


class HeaderError(RuntimeError):
    """Raised when a provider object's georeferencing cannot be established."""


@dataclass(frozen=True)
class Footprint:
    epsg: int
    width: int
    height: int
    resolution_x: float
    resolution_y: float
    bbox_native: tuple[float, float, float, float]


def _read_tags(blob: bytes) -> tuple[dict[int, tuple[int, int, bytes]], str]:
    if blob[:2] not in (b"II", b"MM"):
        raise HeaderError("not a TIFF: bad byte-order mark")
    order = "<" if blob[:2] == b"II" else ">"
    version = struct.unpack(order + "H", blob[2:4])[0]
    if version == 42:
        offset = struct.unpack(order + "I", blob[4:8])[0]
        count = struct.unpack(order + "H", blob[offset : offset + 2])[0]
        entry_size, first = 12, offset + 2
    elif version == 43:  # BigTIFF
        offset = struct.unpack(order + "Q", blob[8:16])[0]
        count = struct.unpack(order + "Q", blob[offset : offset + 8])[0]
        entry_size, first = 20, offset + 8
    else:
        raise HeaderError(f"unsupported TIFF version {version}")

    tags: dict[int, tuple[int, int, bytes]] = {}
    for index in range(count):
        entry = blob[first + index * entry_size : first + (index + 1) * entry_size]
        if len(entry) < entry_size:
            raise HeaderError("directory truncated; header window too small")
        tag, value_type = struct.unpack(order + "HH", entry[:4])
        if version == 42:
            value_count = struct.unpack(order + "I", entry[4:8])[0]
            inline = entry[8:12]
            pointer_format, pointer_width = "I", 4
        else:
            value_count = struct.unpack(order + "Q", entry[4:12])[0]
            inline = entry[12:20]
            pointer_format, pointer_width = "Q", 8
        total = value_count * _TYPE_SIZES.get(value_type, 1)
        if total <= len(inline):
            raw = inline[:total]
        else:
            pointer = struct.unpack(order + pointer_format, inline[:pointer_width])[0]
            if pointer + total > len(blob):
                raise HeaderError(f"tag {tag} payload beyond header window")
            raw = blob[pointer : pointer + total]
        tags[tag] = (value_type, value_count, raw)
    return tags, order


def _values(tags: dict, order: str, tag: int) -> list[float] | None:
    if tag not in tags:
        return None
    value_type, _, raw = tags[tag]
    if value_type == 12:
        return list(struct.unpack(order + "%dd" % (len(raw) // 8), raw))
    if value_type == 3:
        return list(struct.unpack(order + "%dH" % (len(raw) // 2), raw))
    if value_type == 4:
        return list(struct.unpack(order + "%dI" % (len(raw) // 4), raw))
    return None


def read_geotiff_footprint(url: str, *, timeout: int = 120) -> Footprint:
    """Derive a tile's CRS, size and native bounding box from its header bytes."""
    response = requests.get(
        url, headers={"Range": f"bytes=0-{HEADER_BYTES - 1}", "User-Agent": USER_AGENT}, timeout=timeout
    )
    if response.status_code not in (200, 206):
        raise HeaderError(f"HTTP {response.status_code} reading header of {url}")
    tags, order = _read_tags(response.content)

    width = (_values(tags, order, TAG_IMAGE_WIDTH) or [None])[0]
    height = (_values(tags, order, TAG_IMAGE_LENGTH) or [None])[0]
    scale = _values(tags, order, TAG_MODEL_PIXEL_SCALE)
    tiepoint = _values(tags, order, TAG_MODEL_TIEPOINT)
    geo_keys = _values(tags, order, TAG_GEO_KEY_DIRECTORY)
    if not all((width, height, scale, tiepoint, geo_keys)):
        raise HeaderError(f"missing georeferencing tags in {url}")

    epsg = None
    for index in range(4, len(geo_keys), 4):
        if geo_keys[index] == GEO_KEY_PROJECTED_CRS:
            epsg = int(geo_keys[index + 3])
            break
    if epsg is None:
        raise HeaderError(f"no projected CRS geokey in {url}")

    origin_x, origin_y = float(tiepoint[3]), float(tiepoint[4])
    resolution_x, resolution_y = float(scale[0]), float(scale[1])
    return Footprint(
        epsg=epsg,
        width=int(width),
        height=int(height),
        resolution_x=resolution_x,
        resolution_y=resolution_y,
        bbox_native=(
            origin_x,
            origin_y - int(height) * resolution_y,
            origin_x + int(width) * resolution_x,
            origin_y,
        ),
    )


def discover(bbox: str, *, dataset: str = "Digital Elevation Model (DEM) 1 meter", limit: int = 50) -> list[dict]:
    query = urllib.parse.urlencode(
        {"datasets": dataset, "bbox": bbox, "max": limit, "outputFormat": "JSON"}
    )
    response = requests.get(f"{TNM_PRODUCTS_URL}?{query}", timeout=120)
    response.raise_for_status()
    return response.json().get("items", [])


def classify(title: str) -> tuple[str, str, str]:
    """Return ``(dataset_id, dataset_version, manifestation_class)``.

    Adjudication rule, frozen: where several current manifestations give
    complete equivalent coverage of an area of interest, exactly one is
    canonical and the rest are preserved as ALTERNATE_COMPLETE. Puerto Rico
    straddles UTM zones 19N and 20N and USGS publishes the D24 collection in
    both, so zone 19N is fixed as canonical for determinism and zone 20N is
    retained rather than merged. Merging the two projections is only ever valid
    inside an explicit comparison.
    """
    if "D24" in title:
        zone = "19" if " 19 " in title else "20" if " 20 " in title else "?"
        return (
            "USGS_3DEP_1M_PR_PuertoRicoUSVI_D24",
            "D24",
            "CANONICAL" if zone == "19" else "ALTERNATE_COMPLETE",
        )
    return ("USGS_3DEP_1M_PR_PRVI_2018", "2018", "HISTORICAL")


def build_manifestation(item: dict, *, read_header: bool) -> dict[str, Any]:
    url = item.get("downloadURL", "")
    title = item.get("title", "")
    object_id = Path(urllib.parse.urlparse(url).path).stem
    dataset_id, dataset_version, manifestation_class = classify(title)

    record: dict[str, Any] = {
        "Manifestation_ID": f"USGS3DEP:{object_id}",
        "Capability": "DEM",
        "Source_Family": "USGS_3DEP",
        "Dataset_ID": dataset_id,
        "Dataset_Version": dataset_version,
        "Provider_Object_ID": object_id,
        "Provider_Object_Type": "GeoTIFF",
        "Resolution": "1m",
        "Temporal_Class": "SNAPSHOT",
        "Manifestation_Class": manifestation_class,
        "Publication_Date": item.get("publicationDate"),
        "Fetch_Method": "DIRECT_FILE",
        "Fetch_Locator": url,
        "Expected_Bytes": item.get("sizeInBytes"),
        "Expected_SHA256": None,
        "Cache_State": "NOT_CACHED",
        "Metadata_URI": item.get("metaUrl"),
        "Canonicality_Reason": (
            "UTM zone 19N fixed as the deterministic canonical projection for the D24 "
            "collection; zone 20N preserved as an equivalent-coverage alternate."
            if dataset_version == "D24"
            else "Superseded by the D24 collection; retained as historical evidence."
        ),
        "Footprint_Source": "UNRESOLVED",
    }

    if read_header:
        footprint = read_geotiff_footprint(url)
        record.update(
            {
                "Provider_CRS": f"EPSG:{footprint.epsg}",
                "Footprint_BBox_Native": list(footprint.bbox_native),
                "Footprint_Width_Px": footprint.width,
                "Footprint_Height_Px": footprint.height,
                "Footprint_Resolution_M": [footprint.resolution_x, footprint.resolution_y],
                "Footprint_Source": "PROVIDER_HEADER_RANGE_READ",
            }
        )
    return record


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bbox", default="-66.05,18.30,-65.95,18.40", help="W,S,E,N in EPSG:4326")
    parser.add_argument("--output", type=Path, default=REGISTRY_PATH)
    parser.add_argument(
        "--headers-for",
        default="D24",
        help="substring selecting which titles get a header range read (default: D24)",
    )
    args = parser.parse_args(argv)

    items = discover(args.bbox)
    print(f"discovered {len(items)} provider objects over bbox {args.bbox}")

    manifestations: list[dict[str, Any]] = []
    for item in items:
        wants_header = args.headers_for in item.get("title", "")
        try:
            manifestations.append(build_manifestation(item, read_header=wants_header))
        except HeaderError as exc:
            print(f"  header unresolved: {exc}", file=sys.stderr)
            manifestations.append(build_manifestation(item, read_header=False))
        if wants_header:
            print(f"  bound footprint: {manifestations[-1]['Provider_Object_ID']}")

    manifestations.sort(key=lambda record: record["Manifestation_ID"])
    duplicates = len(manifestations) - len({m["Manifestation_ID"] for m in manifestations})
    if duplicates:
        raise SystemExit(f"duplicate provider objects in registry: {duplicates}")

    payload = {
        "schema_version": "spiderweb.source_manifestations.v0.1",
        "capability_scope": ["DEM"],
        "discovery": {"provider": "TNM Access", "bbox_wgs84": args.bbox, "dataset": "1 m DEM"},
        "manifestation_count": len(manifestations),
        "manifestations": manifestations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.output.relative_to(REPO_ROOT)} ({len(manifestations)} manifestations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
