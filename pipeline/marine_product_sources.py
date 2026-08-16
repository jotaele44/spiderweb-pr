"""File-level NCEI product discovery for bounded marine survey universes.

This module operates *after* survey discovery.  It never treats a survey footprint
as a file-level observation and never treats the presence of files as proof that
a rendered feature is real.  Responses are paged, count-closed, and preserve each
returned file row whole.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlencode

from pipeline.marine_sources import (
    BoundingBox,
    CatalogFamily,
    FrozenHttpResponse,
    Transport,
    default_transport,
)

NCEI_CATALOG_BASE = "https://www.ngdc.noaa.gov/next-catalogs/rest"


@dataclass(frozen=True, slots=True)
class ProductFilePage:
    family: CatalogFamily
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


def build_ncei_file_url(
    family: CatalogFamily,
    *,
    surveys: Iterable[str] = (),
    categories: Iterable[str] = (),
    bbox: BoundingBox | None = None,
    offset: int = 0,
    page_size: int = 200,
) -> str:
    if offset < 0:
        raise ValueError("offset must be non-negative")
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    survey_ids = tuple(value.strip() for value in surveys if value.strip())
    if not survey_ids and bbox is None:
        raise ValueError("at least one survey id or a bounding box is required")
    if family is CatalogFamily.SOUNDING and not survey_ids:
        raise ValueError("sounding file discovery requires explicit survey ids")
    params: list[tuple[str, str]] = [
        ("max", str(page_size)),
        ("offset", str(offset)),
    ]
    if survey_ids:
        params.insert(0, ("surveys", ",".join(survey_ids)))
    category_values = tuple(value.strip() for value in categories if value.strip())
    if category_values:
        params.append(("categories", ",".join(category_values)))
    if bbox is not None:
        if family is CatalogFamily.SOUNDING:
            raise ValueError("NCEI sounding file rows do not support file-level geometry filtering")
        params.append(("geometry", bbox.ncei_geometry()))
    return f"{NCEI_CATALOG_BASE}/{family.value}/file?{urlencode(params)}"


def _decode_page(
    family: CatalogFamily,
    frozen: FrozenHttpResponse,
    *,
    offset: int,
    page_size: int,
) -> ProductFilePage:
    if not 200 <= frozen.status < 300:
        raise ValueError(f"HTTP status is not successful: {frozen.status}")
    try:
        payload = json.loads(frozen.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("response is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict) or "message" in payload or "error" in payload:
        raise ValueError(f"NCEI file response is not a valid result object: {payload!r}")
    raw_items = payload.get("items")
    count = payload.get("count")
    if not isinstance(raw_items, list):
        raise ValueError("NCEI file response is missing list field 'items'")
    if not isinstance(count, int) or count < 0:
        raise ValueError("NCEI file response is missing non-negative integer 'count'")
    if len(raw_items) > page_size:
        raise ValueError("NCEI file response exceeds requested page size")
    items: list[dict[str, object]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError("NCEI file items must be JSON objects")
        items.append(dict(item))
    return ProductFilePage(
        family=family,
        request_url=frozen.request_url,
        offset=offset,
        page_size=page_size,
        total_count=count,
        items=tuple(items),
        frozen=frozen,
    )


def fetch_ncei_file_page(
    family: CatalogFamily,
    *,
    surveys: Iterable[str] = (),
    categories: Iterable[str] = (),
    bbox: BoundingBox | None = None,
    offset: int = 0,
    page_size: int = 200,
    transport: Transport = default_transport,
) -> ProductFilePage:
    url = build_ncei_file_url(
        family,
        surveys=surveys,
        categories=categories,
        bbox=bbox,
        offset=offset,
        page_size=page_size,
    )
    frozen = transport(url)
    return _decode_page(family, frozen, offset=offset, page_size=page_size)


def fetch_all_ncei_file_pages(
    family: CatalogFamily,
    *,
    surveys: Iterable[str] = (),
    categories: Iterable[str] = (),
    bbox: BoundingBox | None = None,
    page_size: int = 200,
    transport: Transport = default_transport,
) -> tuple[ProductFilePage, ...]:
    survey_ids = tuple(surveys)
    pages: list[ProductFilePage] = []
    offset = 0
    expected_count: int | None = None
    while True:
        page = fetch_ncei_file_page(
            family,
            surveys=survey_ids,
            categories=categories,
            bbox=bbox,
            offset=offset,
            page_size=page_size,
            transport=transport,
        )
        if expected_count is None:
            expected_count = page.total_count
        elif page.total_count != expected_count:
            raise ValueError("NCEI file count changed during pagination")
        pages.append(page)
        nxt = page.next_offset
        if nxt is None:
            break
        if nxt <= offset:
            raise ValueError("NCEI file pagination did not advance")
        offset = nxt
    observed = sum(len(page.items) for page in pages)
    if expected_count is None or observed != expected_count:
        raise ValueError(
            f"NCEI file pagination did not close arithmetically: observed={observed}, expected={expected_count}"
        )
    return tuple(pages)


def flatten_product_files(pages: Iterable[ProductFilePage]) -> tuple[dict[str, object], ...]:
    return tuple(item for page in pages for item in page.items)
