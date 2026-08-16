"""Direct NOAA product paths used when NEXT file metadata is unavailable."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urljoin

from pipeline.marine_sources import BoundingBox, FrozenHttpResponse, Transport, default_transport


@dataclass(frozen=True, slots=True)
class DirectProductResult:
    request_url: str
    frozen: FrozenHttpResponse
    assets: tuple[dict[str, object], ...]


def fetch_direct(url: str, *, transport: Transport = default_transport) -> FrozenHttpResponse:
    frozen = transport(url)
    if not 200 <= frozen.status < 300:
        raise ValueError(f"HTTP status is not successful: {frozen.status}")
    return frozen


def parse_nos_product_links(frozen: FrozenHttpResponse) -> DirectProductResult:
    try:
        text = frozen.body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("NOS survey page is not UTF-8") from exc
    links: list[dict[str, object]] = []
    seen: set[str] = set()
    for href in re.findall(r'href=["\']([^"\']+)["\']', text, flags=re.I):
        url = urljoin(frozen.request_url, unescape(href))
        low = url.lower()
        if not any(token in low for token in (".bag", ".xyz", ".xml", ".tif", ".pdf")):
            continue
        if url in seen:
            continue
        seen.add(url)
        links.append({"url": url, "kind": low.rsplit(".", 1)[-1].split("?", 1)[0]})
    return DirectProductResult(frozen.request_url, frozen, tuple(links))


def _feature_bbox(feature: dict[str, object]) -> tuple[float, float, float, float] | None:
    raw = feature.get("bbox")
    if isinstance(raw, list) and len(raw) >= 4 and all(isinstance(v, (int, float)) for v in raw[:4]):
        return float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])
    geom = feature.get("geometry")
    if not isinstance(geom, dict):
        return None
    coords = geom.get("coordinates")
    numbers: list[tuple[float, float]] = []
    def walk(value: object) -> None:
        if isinstance(value, list):
            if len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
                numbers.append((float(value[0]), float(value[1])))
            else:
                for child in value:
                    walk(child)
    walk(coords)
    if not numbers:
        return None
    xs = [v[0] for v in numbers]
    ys = [v[1] for v in numbers]
    return min(xs), min(ys), max(xs), max(ys)


def _intersects(extent: tuple[float, float, float, float], bbox: BoundingBox) -> bool:
    x1, y1, x2, y2 = extent
    return not (x2 < bbox.min_lon or x1 > bbox.max_lon or y2 < bbox.min_lat or y1 > bbox.max_lat)


def parse_stac_item_collection(
    frozen: FrozenHttpResponse,
    bbox: BoundingBox,
) -> DirectProductResult:
    try:
        payload = json.loads(frozen.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("STAC item collection is not valid UTF-8 JSON") from exc
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        raise ValueError("STAC item collection is missing features")
    selected: list[dict[str, object]] = []
    for feature in features:
        if not isinstance(feature, dict):
            raise ValueError("STAC feature must be an object")
        extent = _feature_bbox(feature)
        if extent is not None and _intersects(extent, bbox):
            selected.append(dict(feature))
    return DirectProductResult(frozen.request_url, frozen, tuple(selected))
