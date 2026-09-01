"""Bounded direct NOAA archive discovery for independent multibeam roots."""
from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urljoin, urlparse

from pipeline.marine_sources import FrozenHttpResponse, Transport, default_transport

@dataclass(frozen=True, slots=True)
class ArchiveListing:
    request_url: str
    frozen: FrozenHttpResponse
    links: tuple[str, ...]


def fetch_archive_listing(url: str, *, transport: Transport = default_transport) -> ArchiveListing:
    frozen = transport(url)
    if not 200 <= frozen.status < 300:
        raise ValueError(f"HTTP status is not successful: {frozen.status}")
    try:
        text = frozen.body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("archive listing is not UTF-8") from exc
    base = urlparse(url)
    links: list[str] = []
    seen: set[str] = set()
    for href in re.findall(r'href=["\']([^"\']+)["\']', text, flags=re.I):
        target = urljoin(url, unescape(href))
        parsed = urlparse(target)
        if parsed.scheme != "https" or parsed.netloc != base.netloc:
            continue
        if not parsed.path.startswith(base.path):
            continue
        if target == url or target in seen:
            continue
        seen.add(target)
        links.append(target)
    return ArchiveListing(url, frozen, tuple(links))


def product_candidates(links: tuple[str, ...]) -> tuple[str, ...]:
    suffixes = (".gsf", ".xyz", ".asc", ".tif", ".tiff", ".kmz", ".kml", ".xml")
    return tuple(link for link in links if urlparse(link).path.lower().endswith(suffixes))
