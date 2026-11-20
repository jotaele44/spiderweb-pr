"""Fetching a named survey product, inside an explicit byte ceiling.

Everything in :mod:`.acquisition` and :mod:`.discovery` is metadata: it asks
catalogues what they list.  This module is the only place in the package that
fetches a data product, and it is deliberately narrow:

* **named files only** -- a caller passes the exact URLs; nothing is crawled,
  expanded from a pattern or followed from a listing;
* **a separate grant** -- ``PRODUCT_DOWNLOAD`` bounds both the number of files
  and the total bytes.  A metadata grant cannot be spent here, and without a
  grant no request is made;
* **the size is known before a byte is read** -- a response with no declared
  length, a length over the remaining ceiling, or a length that disagrees with
  what the catalogue stated is refused; a body that runs past its declared
  length is aborted and the partial file removed;
* **exact bytes** -- the file is hashed as it is written and a manifest with
  the address, size, hash and retrieval time is written beside it;
* **no redirect, https only, hosts on an allow-list**.

A product that is already held and still matches its manifest is reused
without a request.  Products are large and are never written into the
repository's tracked tree by this module; the caller chooses a runtime
directory.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from pipeline.marine_sources import BoundingBox, FrozenHttpResponse, Transport

from .acquisition import (
    GENERIC_USER_AGENT,
    RECORDED_RESPONSE_HEADERS,
    AcquisitionNotAuthorized,
    Authorization,
    AuthorizationLevel,
    UnexpectedRedirect,
)

PRODUCTS_VERSION = "access-point-products/1.0"
MANIFEST_SCHEMA = "access_point_product_manifest/1.0"
TNM_PRODUCTS_URL = "https://tnmaccess.nationalmap.gov/api/v1/products"
TNM_DEM_1M = "Digital Elevation Model (DEM) 1 meter"
TNM_PROVIDER = "USGS_TNM_ELEVATION_PRODUCTS"
_CHUNK = 1 << 20


class ProductRefused(RuntimeError):
    """A product was not fetched: the reason is in the message."""


class ByteCeilingExceeded(ProductRefused):
    """Fetching the product would pass the authorised byte ceiling."""


class ProductIntegrityError(ValueError):
    """A held product does not match its manifest."""


@dataclass(frozen=True, slots=True)
class ProductRequest:
    """One named file, as a catalogue described it."""

    provider: str
    native_identifier: str
    title: str
    url: str
    size_bytes: int | None = None
    published: str | None = None
    metadata_uri: str | None = None

    def __post_init__(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError(f"a product address must be https: {self.url}")
        if not self.filename:
            raise ValueError(f"a product address must name a file: {self.url}")
        if self.size_bytes is not None and self.size_bytes < 1:
            raise ValueError("size_bytes must be positive when stated")

    @property
    def filename(self) -> str:
        return Path(urlparse(self.url).path).name

    @property
    def host(self) -> str:
        return urlparse(self.url).hostname or ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "native_identifier": self.native_identifier,
            "title": self.title,
            "url": self.url,
            "size_bytes": self.size_bytes,
            "published": self.published,
            "metadata_uri": self.metadata_uri,
        }


@dataclass(frozen=True, slots=True)
class ProductReceipt:
    request: ProductRequest
    path: Path
    size_bytes: int
    sha256: str
    retrieved_utc: str
    headers: Mapping[str, str]
    reused: bool

    def manifest(self) -> dict[str, Any]:
        return {
            "schema": MANIFEST_SCHEMA,
            "products_version": PRODUCTS_VERSION,
            "request": self.request.to_dict(),
            "filename": self.path.name,
            "response_size": self.size_bytes,
            "response_sha256": self.sha256,
            "retrieved_utc": self.retrieved_utc,
            "headers": dict(sorted(self.headers.items())),
        }


def _manifest_path(path: Path) -> Path:
    return path.with_name(path.name + ".manifest.json")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def held_product(
    request: ProductRequest, directory: str | Path
) -> ProductReceipt | None:
    """The product if it is already held and still matches its manifest.

    Returns ``None`` when nothing is held.  A file that is present but no
    longer matches is an integrity error, never silently re-fetched.
    """

    path = Path(directory) / request.filename
    manifest_path = _manifest_path(path)
    if not path.is_file() and not manifest_path.is_file():
        return None
    if not path.is_file() or not manifest_path.is_file():
        raise ProductIntegrityError(
            f"{request.filename}: the file and its manifest must both be present"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ProductIntegrityError(f"{manifest_path.name} is not a product manifest")
    if manifest["request"]["url"] != request.url:
        raise ProductIntegrityError(
            f"{request.filename} was fetched from a different address"
        )
    size = path.stat().st_size
    if (
        size != manifest["response_size"]
        or _sha256_file(path) != manifest["response_sha256"]
    ):
        raise ProductIntegrityError(f"{request.filename} does not match its manifest")
    return ProductReceipt(
        request=request,
        path=path,
        size_bytes=size,
        sha256=str(manifest["response_sha256"]),
        retrieved_utc=str(manifest["retrieved_utc"]),
        headers=dict(manifest.get("headers") or {}),
        reused=True,
    )


class DownloadSession:
    """Spends one product grant.  Counts files and bytes across calls."""

    def __init__(
        self,
        authorization: Authorization,
        *,
        allowed_hosts: Sequence[str],
        opener: Callable[..., Any] = urlopen,
        user_agent: str = GENERIC_USER_AGENT,
        timeout: float = 120.0,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if not allowed_hosts:
            raise ValueError("at least one allowed host is required")
        self.authorization = authorization
        self.allowed_hosts = frozenset(h.lower() for h in allowed_hosts)
        self._opener = opener
        self._user_agent = user_agent
        self._timeout = timeout
        self._clock = clock
        self.files_fetched = 0
        self.bytes_fetched = 0

    @property
    def bytes_remaining(self) -> int:
        return self.authorization.max_bytes - self.bytes_fetched

    def fetch(self, request: ProductRequest, directory: str | Path) -> ProductReceipt:
        held = held_product(request, directory)
        if held is not None:
            return held
        if self.authorization.level is not AuthorizationLevel.PRODUCT_DOWNLOAD:
            raise AcquisitionNotAuthorized(
                f"PRODUCT_DOWNLOAD is not authorised (grant is "
                f"{self.authorization.level.value}); nothing was requested"
            )
        if request.host.lower() not in self.allowed_hosts:
            raise ProductRefused(f"{request.host} is not an allowed product host")
        if self.files_fetched >= self.authorization.max_requests:
            raise ProductRefused(
                f"the authorised number of files ({self.authorization.max_requests}) "
                "is used up"
            )
        if request.size_bytes is not None and request.size_bytes > self.bytes_remaining:
            raise ByteCeilingExceeded(
                f"{request.filename} is stated as {request.size_bytes} bytes; "
                f"{self.bytes_remaining} remain under the ceiling.  Nothing was requested"
            )

        target = Path(directory) / request.filename
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        http_request = Request(request.url, headers={"User-Agent": self._user_agent})
        digest = hashlib.sha256()
        written = 0
        try:
            with self._opener(http_request, timeout=self._timeout) as response:
                if response.geturl() != request.url:
                    raise UnexpectedRedirect(
                        f"{request.url} answered from {response.geturl()}"
                    )
                if int(response.status) != 200:
                    raise ProductRefused(
                        f"{request.filename}: HTTP status {response.status}"
                    )
                declared = response.headers.get("Content-Length")
                if declared is None or not str(declared).isdigit():
                    raise ProductRefused(
                        f"{request.filename}: the server declared no length, so the "
                        "ceiling cannot be checked before reading"
                    )
                length = int(declared)
                if request.size_bytes is not None and length != request.size_bytes:
                    raise ProductRefused(
                        f"{request.filename}: the server declares {length} bytes but "
                        f"the catalogue stated {request.size_bytes}"
                    )
                if length > self.bytes_remaining:
                    raise ByteCeilingExceeded(
                        f"{request.filename} is {length} bytes; {self.bytes_remaining} "
                        "remain under the ceiling.  The body was not read"
                    )
                headers = {
                    str(k): str(v)
                    for k, v in response.headers.items()
                    if str(k).lower() in RECORDED_RESPONSE_HEADERS
                }
                with partial.open("wb") as handle:
                    while True:
                        chunk = response.read(_CHUNK)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > length:
                            raise ProductRefused(
                                f"{request.filename}: the body ran past its declared "
                                "length; the transfer was aborted"
                            )
                        digest.update(chunk)
                        handle.write(chunk)
            if written != length:
                raise ProductRefused(
                    f"{request.filename}: {written} bytes arrived of {length} declared"
                )
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        partial.replace(target)
        self.files_fetched += 1
        self.bytes_fetched += written
        receipt = ProductReceipt(
            request=request,
            path=target,
            size_bytes=written,
            sha256=digest.hexdigest(),
            retrieved_utc=self._clock().isoformat(timespec="seconds"),
            headers=headers,
            reused=False,
        )
        _manifest_path(target).write_text(
            json.dumps(receipt.manifest(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return receipt


# -- the USGS elevation product catalogue (metadata) -----------------------


def tnm_products_url(
    bbox: BoundingBox, *, dataset: str = TNM_DEM_1M, limit: int = 50
) -> str:
    if not 1 <= limit <= 200:
        raise ValueError("limit must be within [1, 200]")
    return (
        TNM_PRODUCTS_URL
        + "?"
        + urlencode(
            {
                "datasets": dataset,
                "bbox": bbox.ncei_geometry(),
                "prodFormats": "GeoTIFF",
                "max": limit,
            }
        )
    )


def tnm_elevation_products(
    bbox: BoundingBox, *, transport: Transport, dataset: str = TNM_DEM_1M
) -> tuple[FrozenHttpResponse, list[ProductRequest]]:
    """Elevation products the USGS catalogue lists for a box.  Metadata only.

    The catalogue must return everything it reports (``total`` equals the rows
    received); a truncated answer is an error, not a shorter list.
    """

    frozen = transport(tnm_products_url(bbox, dataset=dataset))
    if frozen.status != 200:
        raise ValueError(f"product catalogue answered HTTP {frozen.status}")
    payload = json.loads(frozen.body)
    items = payload.get("items")
    if not isinstance(items, list) or not isinstance(payload.get("total"), int):
        raise ValueError("product catalogue answer is missing 'items' or 'total'")
    if payload["total"] != len(items):
        raise ValueError(
            f"product catalogue reports {payload['total']} products but returned "
            f"{len(items)}; refusing a truncated list"
        )
    products = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("product catalogue rows must be objects")
        source = str(item.get("sourceId") or "").strip()
        url = str(item.get("downloadURL") or "").strip()
        if not source or not url:
            raise ValueError("product catalogue row has no identifier or address")
        size = item.get("sizeInBytes")
        products.append(
            ProductRequest(
                provider=TNM_PROVIDER,
                native_identifier=f"TNM:{source}",
                title=str(item.get("title") or source),
                url=url,
                size_bytes=int(size) if isinstance(size, int) and size > 0 else None,
                published=(
                    str(item["publicationDate"])
                    if item.get("publicationDate")
                    else None
                ),
                metadata_uri=(str(item["metaUrl"]) if item.get("metaUrl") else None),
            )
        )
    ids = [p.native_identifier for p in products]
    if len(ids) != len(set(ids)):
        raise ValueError("product catalogue returned a repeated identifier")
    return frozen, sorted(products, key=lambda p: p.native_identifier)
