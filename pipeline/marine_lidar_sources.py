"""NOAA/USIEI lidar inventory and bulk-product acquisition controls.

The US Interagency Elevation Inventory is a discovery/coverage source.  Its
features are metadata polygons, not depth measurements.  This module therefore
keeps footprint discovery separate from downstream per-sample observation
binding.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable
from urllib.parse import urlencode, urljoin, urlparse

from pipeline.marine_sources import (
    BoundingBox,
    FrozenHttpResponse,
    Transport,
    default_transport,
)


USIEI_BASE = (
    "https://coast.noaa.gov/arcgis/rest/services/"
    "USInteragencyElevationInventory/USInteragencyElevInventory/MapServer"
)


class LidarInventoryLayer(IntEnum):
    TOPOBATHY_SHORELINE = 0
    TOPOGRAPHIC = 1
    BATHYMETRIC = 2
    IFSAR = 3
    OTHER_BATHYMETRIC_SURVEYS = 4


@dataclass(frozen=True, slots=True)
class LidarInventoryPage:
    layer: LidarInventoryLayer
    request_url: str
    offset: int
    page_size: int
    features: tuple[dict[str, object], ...]
    exceeded_transfer_limit: bool
    frozen: FrozenHttpResponse

    @property
    def next_offset(self) -> int | None:
        if not self.exceeded_transfer_limit:
            return None
        if not self.features:
            raise ValueError("USIEI transfer limit set on an empty page")
        return self.offset + len(self.features)


@dataclass(frozen=True, slots=True)
class BulkProductManifest:
    dataset_id: str
    index_url: str
    assets: tuple[str, ...]
    frozen: FrozenHttpResponse

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise ValueError("dataset_id must not be empty")
        if len(set(self.assets)) != len(self.assets):
            raise ValueError("bulk-product asset URLs must be unique")


def _decode_json(frozen: FrozenHttpResponse) -> dict[str, object]:
    if not 200 <= frozen.status < 300:
        raise ValueError(f"HTTP status is not successful: {frozen.status}")
    try:
        payload = json.loads(frozen.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("response is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("response JSON root must be an object")
    if "error" in payload:
        raise ValueError(f"source returned error object: {payload['error']!r}")
    return payload


def build_usiei_query_url(
    layer: LidarInventoryLayer,
    bbox: BoundingBox,
    *,
    offset: int = 0,
    page_size: int = 2000,
    where: str = "1=1",
) -> str:
    if offset < 0:
        raise ValueError("offset must be non-negative")
    if not 1 <= page_size <= 10000:
        raise ValueError("page_size must be within the USIEI max record count")
    if not where.strip():
        raise ValueError("where must not be empty")
    params = [
        ("f", "json"),
        ("where", where),
        ("geometry", bbox.esri_envelope()),
        ("geometryType", "esriGeometryEnvelope"),
        ("inSR", "4326"),
        ("spatialRel", "esriSpatialRelIntersects"),
        ("outFields", "*"),
        ("returnGeometry", "true"),
        ("outSR", "4326"),
        ("resultOffset", str(offset)),
        ("resultRecordCount", str(page_size)),
        ("orderByFields", "OBJECTID ASC"),
    ]
    return f"{USIEI_BASE}/{int(layer)}/query?{urlencode(params)}"


def fetch_usiei_page(
    layer: LidarInventoryLayer,
    bbox: BoundingBox,
    *,
    offset: int = 0,
    page_size: int = 2000,
    where: str = "1=1",
    transport: Transport = default_transport,
) -> LidarInventoryPage:
    url = build_usiei_query_url(
        layer, bbox, offset=offset, page_size=page_size, where=where
    )
    frozen = transport(url)
    payload = _decode_json(frozen)
    raw = payload.get("features")
    if not isinstance(raw, list):
        raise ValueError("USIEI response is missing list field 'features'")
    if len(raw) > page_size:
        raise ValueError("USIEI returned more features than requested")
    features: list[dict[str, object]] = []
    for feature in raw:
        if not isinstance(feature, dict):
            raise ValueError("USIEI features must be objects")
        features.append(dict(feature))
    exceeded = payload.get("exceededTransferLimit", False)
    if not isinstance(exceeded, bool):
        raise ValueError("exceededTransferLimit must be boolean")
    return LidarInventoryPage(
        layer=layer,
        request_url=url,
        offset=offset,
        page_size=page_size,
        features=tuple(features),
        exceeded_transfer_limit=exceeded,
        frozen=frozen,
    )


def fetch_all_usiei_pages(
    layer: LidarInventoryLayer,
    bbox: BoundingBox,
    *,
    page_size: int = 2000,
    where: str = "1=1",
    transport: Transport = default_transport,
) -> tuple[LidarInventoryPage, ...]:
    pages: list[LidarInventoryPage] = []
    offset = 0
    while True:
        page = fetch_usiei_page(
            layer,
            bbox,
            offset=offset,
            page_size=page_size,
            where=where,
            transport=transport,
        )
        pages.append(page)
        nxt = page.next_offset
        if nxt is None:
            break
        if nxt <= offset:
            raise ValueError("USIEI pagination did not advance")
        offset = nxt
    return tuple(pages)


def _validate_https_asset(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"bulk asset must be an absolute HTTPS URL: {url!r}")
    return url


def parse_url_list(body: bytes, *, base_url: str | None = None) -> tuple[str, ...]:
    """Parse NOAA bulk ``urllist*.txt`` content without inventing missing assets."""

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("bulk URL list is not UTF-8") from exc
    assets: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        candidate = urljoin(base_url, line) if base_url else line
        assets.append(_validate_https_asset(candidate))
    if len(set(assets)) != len(assets):
        raise ValueError("bulk URL list contains duplicate asset URLs")
    return tuple(assets)


def fetch_bulk_url_manifest(
    dataset_id: str,
    url_list_url: str,
    *,
    transport: Transport = default_transport,
) -> BulkProductManifest:
    _validate_https_asset(url_list_url)
    frozen = transport(url_list_url)
    if not 200 <= frozen.status < 300:
        raise ValueError(f"HTTP status is not successful: {frozen.status}")
    assets = parse_url_list(frozen.body, base_url=url_list_url)
    return BulkProductManifest(
        dataset_id=dataset_id,
        index_url=url_list_url,
        assets=assets,
        frozen=frozen,
    )


def flatten_inventory_features(
    pages: Iterable[LidarInventoryPage],
) -> tuple[dict[str, object], ...]:
    """Preserve every returned feature; no project-name deduplication is performed."""

    return tuple(feature for page in pages for feature in page.features)
