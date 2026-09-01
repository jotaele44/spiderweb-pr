"""Authoritative marine-source discovery and acquisition controls.

The adapters in this module intentionally separate source discovery from
interpretation.  They build deterministic NOAA/NCEI queries, preserve paged
responses whole-row, and freeze exact response bytes with request identity and
SHA-256 before downstream marine analysis.

No source is considered exhaustive merely because a search returned zero rows;
callers must close the bounded query universe and page arithmetic before making
coverage claims.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Callable, Iterable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen


NCEI_CATALOG_BASE = "https://www.ngdc.noaa.gov/next-catalogs/rest"
NCEI_NOS_BAGS_LAYER = (
    "https://gis.ngdc.noaa.gov/arcgis/rest/services/"
    "web_mercator/nos_hydro_dynamic/MapServer/0"
)


class CatalogFamily(StrEnum):
    MULTIBEAM = "multibeam"
    SOUNDING = "sounding"


@dataclass(frozen=True, slots=True)
class BoundingBox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def __post_init__(self) -> None:
        if not (-180 <= self.min_lon <= 180 and -180 <= self.max_lon <= 180):
            raise ValueError("longitude must be within [-180, 180]")
        if not (-90 <= self.min_lat <= 90 and -90 <= self.max_lat <= 90):
            raise ValueError("latitude must be within [-90, 90]")
        if self.min_lon >= self.max_lon or self.min_lat >= self.max_lat:
            raise ValueError("bounding box minimums must be less than maximums")

    def ncei_geometry(self) -> str:
        return ",".join(
            str(value)
            for value in (self.min_lon, self.min_lat, self.max_lon, self.max_lat)
        )

    def esri_envelope(self) -> str:
        return self.ncei_geometry()


@dataclass(frozen=True, slots=True)
class FrozenHttpResponse:
    request_url: str
    status: int
    retrieved_utc: str
    response_sha256: str
    response_size: int
    headers: Mapping[str, str]
    body: bytes

    def manifest(self) -> dict[str, object]:
        return {
            "request_url": self.request_url,
            "status": self.status,
            "retrieved_utc": self.retrieved_utc,
            "response_sha256": self.response_sha256,
            "response_size": self.response_size,
            "headers": dict(sorted(self.headers.items())),
        }


@dataclass(frozen=True, slots=True)
class CatalogPage:
    request_url: str
    offset: int
    page_size: int
    total_count: int
    items: tuple[dict[str, object], ...]
    frozen: FrozenHttpResponse

    @property
    def next_offset(self) -> int | None:
        candidate = self.offset + len(self.items)
        if candidate >= self.total_count or not self.items:
            return None
        return candidate


@dataclass(frozen=True, slots=True)
class ArcGISPage:
    request_url: str
    offset: int
    page_size: int
    features: tuple[dict[str, object], ...]
    exceeded_transfer_limit: bool
    frozen: FrozenHttpResponse

    @property
    def next_offset(self) -> int | None:
        if not self.exceeded_transfer_limit or not self.features:
            return None
        return self.offset + len(self.features)


Transport = Callable[[str], FrozenHttpResponse]


def build_ncei_catalog_url(
    family: CatalogFamily,
    bbox: BoundingBox,
    *,
    offset: int = 0,
    page_size: int = 100,
    start_year: int | None = None,
    end_year: int | None = None,
    surveys: Iterable[str] = (),
    platforms: Iterable[str] = (),
) -> str:
    """Build a deterministic NCEI catalog survey query URL."""

    if offset < 0:
        raise ValueError("offset must be non-negative")
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    if start_year is not None and end_year is not None and start_year > end_year:
        raise ValueError("start_year must not exceed end_year")

    params: list[tuple[str, str]] = [
        ("geometry", bbox.ncei_geometry()),
        ("max", str(page_size)),
        ("offset", str(offset)),
    ]
    if start_year is not None:
        params.append(("startYear", str(start_year)))
    if end_year is not None:
        params.append(("endYear", str(end_year)))

    survey_values = tuple(value for value in surveys if value)
    platform_values = tuple(value for value in platforms if value)
    if survey_values:
        params.append(("surveys", ",".join(survey_values)))
    if platform_values:
        params.append(("platforms", ",".join(platform_values)))

    return f"{NCEI_CATALOG_BASE}/{family.value}/catalog/survey?{urlencode(params)}"


def build_nos_bag_query_url(
    bbox: BoundingBox,
    *,
    offset: int = 0,
    page_size: int = 1000,
    where: str = "1=1",
) -> str:
    """Build a deterministic ArcGIS query against the NOS surveys-with-BAGs layer."""

    if offset < 0:
        raise ValueError("offset must be non-negative")
    if not (1 <= page_size <= 2000):
        raise ValueError("page_size must be between 1 and the layer max of 2000")
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
        ("orderByFields", "SURVEY_ID ASC"),
    ]
    return f"{NCEI_NOS_BAGS_LAYER}/query?{urlencode(params)}"


def default_transport(url: str, *, timeout: float = 60.0) -> FrozenHttpResponse:
    """Fetch and freeze exact response bytes from an authoritative source."""

    request = Request(url, headers={"User-Agent": "spiderweb-pr/0.1 marine-source-adapter"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https URLs
        body = response.read()
        status = int(getattr(response, "status", response.getcode()))
        headers = {str(k): str(v) for k, v in response.headers.items()}
        final_url = response.geturl()

    return FrozenHttpResponse(
        request_url=final_url,
        status=status,
        retrieved_utc=datetime.now(timezone.utc).isoformat(),
        response_sha256=hashlib.sha256(body).hexdigest(),
        response_size=len(body),
        headers=headers,
        body=body,
    )


def _decode_json_object(frozen: FrozenHttpResponse) -> dict[str, object]:
    if frozen.status < 200 or frozen.status >= 300:
        raise ValueError(f"HTTP status is not successful: {frozen.status}")
    try:
        decoded = json.loads(frozen.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("response is not valid UTF-8 JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("response JSON root must be an object")
    if "error" in decoded:
        raise ValueError(f"source returned error object: {decoded['error']!r}")
    return decoded


def fetch_ncei_catalog_page(
    family: CatalogFamily,
    bbox: BoundingBox,
    *,
    offset: int = 0,
    page_size: int = 100,
    start_year: int | None = None,
    end_year: int | None = None,
    surveys: Iterable[str] = (),
    platforms: Iterable[str] = (),
    transport: Transport = default_transport,
) -> CatalogPage:
    url = build_ncei_catalog_url(
        family,
        bbox,
        offset=offset,
        page_size=page_size,
        start_year=start_year,
        end_year=end_year,
        surveys=surveys,
        platforms=platforms,
    )
    frozen = transport(url)
    payload = _decode_json_object(frozen)

    raw_items = payload.get("items")
    count = payload.get("count")
    if not isinstance(raw_items, list):
        raise ValueError("NCEI catalog response is missing list field 'items'")
    if not isinstance(count, int) or count < 0:
        raise ValueError("NCEI catalog response is missing non-negative integer 'count'")
    if len(raw_items) > page_size:
        raise ValueError("NCEI catalog returned more rows than requested page size")
    if offset + len(raw_items) > count:
        raise ValueError("NCEI catalog page arithmetic exceeds total count")

    items: list[dict[str, object]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError("NCEI catalog items must be JSON objects")
        items.append(dict(item))

    return CatalogPage(
        request_url=url,
        offset=offset,
        page_size=page_size,
        total_count=count,
        items=tuple(items),
        frozen=frozen,
    )


def fetch_all_ncei_catalog_pages(
    family: CatalogFamily,
    bbox: BoundingBox,
    *,
    page_size: int = 100,
    start_year: int | None = None,
    end_year: int | None = None,
    transport: Transport = default_transport,
) -> tuple[CatalogPage, ...]:
    """Exhaust the bounded catalog query using returned count/offset arithmetic."""

    pages: list[CatalogPage] = []
    offset = 0
    expected_count: int | None = None
    while True:
        page = fetch_ncei_catalog_page(
            family,
            bbox,
            offset=offset,
            page_size=page_size,
            start_year=start_year,
            end_year=end_year,
            transport=transport,
        )
        if expected_count is None:
            expected_count = page.total_count
        elif page.total_count != expected_count:
            raise ValueError("NCEI total count changed during pagination")
        pages.append(page)
        if page.next_offset is None:
            break
        if page.next_offset <= offset:
            raise ValueError("NCEI pagination did not advance")
        offset = page.next_offset

    retained = sum(len(page.items) for page in pages)
    if expected_count is None or retained != expected_count:
        raise ValueError(
            f"NCEI pagination failed arithmetic closure: retained={retained}, "
            f"expected={expected_count}"
        )
    return tuple(pages)


def fetch_nos_bag_page(
    bbox: BoundingBox,
    *,
    offset: int = 0,
    page_size: int = 1000,
    where: str = "1=1",
    transport: Transport = default_transport,
) -> ArcGISPage:
    url = build_nos_bag_query_url(
        bbox, offset=offset, page_size=page_size, where=where
    )
    frozen = transport(url)
    payload = _decode_json_object(frozen)

    raw_features = payload.get("features")
    if not isinstance(raw_features, list):
        raise ValueError("ArcGIS response is missing list field 'features'")
    if len(raw_features) > page_size:
        raise ValueError("ArcGIS returned more features than requested page size")
    features: list[dict[str, object]] = []
    for feature in raw_features:
        if not isinstance(feature, dict):
            raise ValueError("ArcGIS features must be JSON objects")
        features.append(dict(feature))

    exceeded = payload.get("exceededTransferLimit", False)
    if not isinstance(exceeded, bool):
        raise ValueError("exceededTransferLimit must be boolean when supplied")

    return ArcGISPage(
        request_url=url,
        offset=offset,
        page_size=page_size,
        features=tuple(features),
        exceeded_transfer_limit=exceeded,
        frozen=frozen,
    )


def fetch_all_nos_bag_pages(
    bbox: BoundingBox,
    *,
    page_size: int = 1000,
    where: str = "1=1",
    transport: Transport = default_transport,
) -> tuple[ArcGISPage, ...]:
    pages: list[ArcGISPage] = []
    offset = 0
    while True:
        page = fetch_nos_bag_page(
            bbox,
            offset=offset,
            page_size=page_size,
            where=where,
            transport=transport,
        )
        pages.append(page)
        if page.next_offset is None:
            break
        if page.next_offset <= offset:
            raise ValueError("ArcGIS pagination did not advance")
        offset = page.next_offset
    return tuple(pages)


def freeze_http_response(
    frozen: FrozenHttpResponse,
    directory: str | Path,
    *,
    stem: str,
) -> tuple[Path, Path]:
    """Persist exact bytes and a deterministic sidecar manifest.

    The raw response bytes are never regenerated from parsed JSON.  The manifest
    is a separate logical artifact and does not claim byte identity with the
    response body.
    """

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    body_path = root / f"{stem}.bin"
    manifest_path = root / f"{stem}.manifest.json"
    body_path.write_bytes(frozen.body)
    manifest_path.write_text(
        json.dumps(frozen.manifest(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if hashlib.sha256(body_path.read_bytes()).hexdigest() != frozen.response_sha256:
        raise ValueError("persisted response bytes failed SHA-256 verification")
    return body_path, manifest_path
