"""Import a bounded STAC collection into the existing exact-footprint planner.

Three independently frozen inputs are required: Collection, ItemCollection and
provider URL list. This never downloads raster/point-cloud assets. Source IDs,
self links, asset keys and exact URL sets bind the records; filenames do not.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .aoi_planner import MAX_CATALOG_BYTES, MAX_ROWS, canonical_bytes, digest, strict_json


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def approved_url(url: str, prefixes: list[str]) -> str:
    require(isinstance(url, str) and url == url.strip(), "INVALID_URL")
    parsed = urlsplit(url)
    require(parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username
            and not parsed.password and parsed.port in (None, 443)
            and not parsed.query and not parsed.fragment, "UNAPPROVED_URL")
    require("\\" not in url and not any(c in url for c in "\r\n\t")
            and ".." not in unquote(parsed.path).split("/"), "UNSAFE_URL_PATH")
    require(any(url.startswith(prefix) and prefix.endswith("/") for prefix in prefixes),
            "URL_OUTSIDE_APPROVED_DATASET_PREFIX")
    return url


def relation_sets(a: list[str], b: list[str]) -> dict:
    left, right = set(a), set(b)
    return {"INTERSECTION": sorted(left & right), "A_ONLY": sorted(left - right),
            "B_ONLY": sorted(right - left), "UNION": sorted(left | right),
            "SYMMETRIC_DIFFERENCE": sorted(left ^ right)}


def _links(doc: dict, rel: str, base: str, prefixes: list[str]) -> list[str]:
    links = doc.get("links", [])
    require(isinstance(links, list) and all(isinstance(link, dict) for link in links), "INVALID_LINKS")
    require(not any(link.get("rel") in {"next", "child"} for link in links), "PAGINATED_OR_HIERARCHICAL_INPUT_NOT_CLOSED")
    values = []
    for link in links:
        if link.get("rel") == rel:
            href = link.get("href")
            require(isinstance(href, str) and bool(href), "MISSING_LINK_HREF")
            values.append(approved_url(urljoin(base, href), prefixes))
    require(len(values) == len(set(values)), f"DUPLICATE_{rel.upper()}_LINK")
    return values


def convert_snapshot(collection_raw: bytes, items_raw: bytes, urls_raw: bytes, spec: dict) -> tuple[dict, dict]:
    for raw in (collection_raw, items_raw, urls_raw):
        require(isinstance(raw, bytes) and len(raw) <= MAX_CATALOG_BYTES, "SOURCE_BYTE_LIMIT")
    collection, items = strict_json(collection_raw), strict_json(items_raw)
    require(isinstance(collection, dict) and collection.get("type") == "Collection", "NOT_A_COLLECTION")
    require(collection.get("id") == spec["collection_id_raw"], "COLLECTION_ID_MISMATCH")
    require(isinstance(items, dict) and items.get("type") == "FeatureCollection", "NOT_AN_ITEMCOLLECTION")
    require("crs" not in collection and "crs" not in items, "STAC_CRS_MEMBER_REQUIRES_REVIEW")
    prefixes = spec["approved_url_prefixes"]
    expected_items = _links(collection, "item", spec["collection_url"], prefixes)
    require(bool(expected_items), "EMPTY_COLLECTION_DENOMINATOR")
    _links(items, "self", spec["items_url"], prefixes)  # also reject unconsumed pagination
    features = items.get("features")
    require(isinstance(features, list) and 0 < len(features) <= MAX_ROWS, "INVALID_ITEM_DENOMINATOR")
    for key in ("numberMatched", "numberReturned"):
        if key in items:
            require(type(items[key]) is int and items[key] == len(features), "INCOMPLETE_ITEMCOLLECTION")
    source_ids, self_links, asset_urls, rows, asset_receipts = [], [], [], [], []
    for index, item in enumerate(features):
        require(isinstance(item, dict) and item.get("type") == "Feature", "INVALID_ITEM")
        require("crs" not in item, "STAC_CRS_MEMBER_REQUIRES_REVIEW")
        require(item.get("stac_version") in {"1.0.0", "1.1.0"}, "UNSUPPORTED_STAC_VERSION")
        item_id = item.get("id")
        require(isinstance(item_id, str) and bool(item_id), "MISSING_STABLE_ITEM_ID")
        source_ids.append(item_id)
        require(item.get("collection") == collection["id"], "ITEM_COLLECTION_BINDING_MISMATCH")
        self_urls = _links(item, "self", spec["items_url"], prefixes)
        require(len(self_urls) == 1, "EXACT_ITEM_SELF_LINK_REQUIRED")
        self_url = self_urls[0]; self_links.append(self_url)
        properties, assets = item.get("properties"), item.get("assets")
        require(isinstance(properties, dict) and isinstance(assets, dict) and bool(assets), "INVALID_ITEM_PROPERTIES_OR_ASSETS")
        data_count = 0
        for key, asset in assets.items():
            require(isinstance(key, str) and isinstance(asset, dict), "INVALID_ASSET")
            roles = asset.get("roles", [])
            require(isinstance(roles, list) and all(isinstance(role, str) for role in roles), "INVALID_ASSET_ROLES")
            declared = key in spec.get("data_asset_keys", [])
            data = "data" in roles or declared
            if not data:
                require(bool(set(roles) & {"metadata", "thumbnail", "overview"}), "UNCLASSIFIED_ASSET_REQUIRES_REVIEW")
                asset_receipts.append({"item_id": item_id, "asset_key_raw": key, "state": "AUXILIARY", "raw_asset": copy.deepcopy(asset)})
                continue
            data_count += 1
            require("proj:geometry" not in asset and "geometry" not in asset, "PER_ASSET_GEOMETRY_REQUIRES_ADAPTER")
            href = asset.get("href")
            require(isinstance(href, str) and bool(href), "DATA_ASSET_URL_UNBOUND")
            url = approved_url(urljoin(self_url, href), prefixes)
            require(urlsplit(url).path.lower().endswith(tuple(spec["data_suffixes"])), "UNEXPECTED_DATA_ASSET_TYPE")
            asset_urls.append(url)
            size = asset.get("file:size")
            require(size is None or (type(size) is int and size >= 0), "INVALID_FILE_SIZE")
            # STAC datetime is not automatically the lidar collection date.
            # Missing acquisition metadata/resolution remains unknown to filters.
            asset_id = json.dumps([item_id, key], ensure_ascii=True, separators=(",", ":"))
            row = {"type": "Feature", "geometry": copy.deepcopy(item.get("geometry")), "properties": {
                "asset_id": asset_id, "source_url": url, "product": spec["dataset_class"],
                "size_bytes": size, "acquisition_date": None, "resolution_m": None,
                "source_item_id_raw": item_id, "stac_asset_key_raw": key,
                "upstream_item_index": index, "upstream_item_self_url": self_url,
                "geometry_basis": "PUBLISHED_STAC_ITEM_FOOTPRINT_NOT_VALID_DATA_MASK",
                "stac_datetime_raw": properties.get("datetime"),
                "upstream_item_sha256_logical": digest(item), "raw_asset": copy.deepcopy(asset)}}
            rows.append(row)
            asset_receipts.append({"item_id": item_id, "asset_key_raw": key, "state": "DATA", "source_url": url})
        require(data_count > 0, "ITEM_WITHOUT_CLASSIFIED_DATA")
        require(data_count == 1, "MULTIPLE_DATA_ASSETS_REQUIRE_PER_ASSET_FOOTPRINTS")
    require(len(source_ids) == len(set(source_ids)), "DUPLICATE_ITEM_ID")
    require(len(self_links) == len(set(self_links)), "DUPLICATE_ITEM_SELF_LINK")
    item_relation = relation_sets(expected_items, self_links)
    require(not item_relation["SYMMETRIC_DIFFERENCE"], "COLLECTION_ITEM_SET_MISMATCH")
    text = urls_raw.decode("utf-8-sig", errors="strict")
    raw_lines = text.splitlines()
    expected_urls = []
    for line in raw_lines:
        if not line:
            continue
        url = approved_url(line, prefixes)
        require(urlsplit(url).path.lower().endswith(tuple(spec["data_suffixes"])), "UNCLASSIFIED_URL_LIST_ENTRY")
        expected_urls.append(url)
    require(bool(expected_urls), "EMPTY_URL_LIST")
    require(len(expected_urls) == len(set(expected_urls)), "DUPLICATE_URL_LIST_ENTRY")
    require(len(asset_urls) == len(set(asset_urls)), "REPEATED_ASSET_URL_REQUIRES_ADJUDICATION")
    url_relation = relation_sets(expected_urls, asset_urls)
    require(not url_relation["SYMMETRIC_DIFFERENCE"] and Counter(expected_urls) == Counter(asset_urls), "ASSET_URL_SET_MISMATCH")
    require(len(rows) <= MAX_ROWS, "OUTPUT_ROW_LIMIT")
    result = {"type": "FeatureCollection", "features": rows}
    require(len(canonical_bytes(result)) <= MAX_CATALOG_BYTES, "OUTPUT_BYTE_LIMIT")
    receipt = {"schema_version": "aoi_stac_snapshot.v1.0", "dataset_id": spec["dataset_id"],
               "collection_id_raw": collection["id"], "items": len(features), "data_assets": len(rows),
               "auxiliary_assets": sum(r["state"] == "AUXILIARY" for r in asset_receipts),
               "asset_classification": asset_receipts, "collection_item_relation": item_relation,
               "data_url_relation": url_relation, "input_hashes": {
                   "collection": hashlib.sha256(collection_raw).hexdigest(),
                   "items": hashlib.sha256(items_raw).hexdigest(), "urls": hashlib.sha256(urls_raw).hexdigest()},
               "catalog_sha256": hashlib.sha256(canonical_bytes(result)).hexdigest(),
               "scope": "this_collection_snapshot_only", "upstream_authenticity": "REVIEW_SOURCE_RECEIPTS",
               "coverage": "UNKNOWN", "source_equivalence": "NOT_INFERRED", "arithmetic_closed": True}
    return result, receipt


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("SOURCE_REDIRECT_REQUIRES_REVIEW")


def write_once(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.read_bytes() == raw, "IMMUTABLE_SNAPSHOT_CONFLICT")
        return
    # Publish only completed files. A failed source fetch cannot become an input.
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".partial-", delete=False) as file:
        temp = Path(file.name)
        file.write(raw); file.flush(); os.fsync(file.fileno())
    try:
        try:
            os.link(temp, path)  # no overwrite, including concurrent writers
        except FileExistsError:
            require(path.read_bytes() == raw, "IMMUTABLE_SNAPSHOT_CONFLICT")
    finally:
        temp.unlink(missing_ok=True)


def acquire_metadata(url: str, directory: Path, name: str, prefixes: list[str]) -> tuple[bytes, dict]:
    approved_url(url, prefixes)
    path, receipt_path = directory / name, directory / (name + ".receipt.json")
    if path.exists() or receipt_path.exists():
        require(path.is_file() and receipt_path.is_file(), "INCOMPLETE_PRIOR_SNAPSHOT")
        raw, receipt = path.read_bytes(), strict_json(receipt_path.read_bytes())
        require(receipt.get("url") == url and receipt.get("sha256") == hashlib.sha256(raw).hexdigest(), "PRIOR_SNAPSHOT_MISMATCH")
        return raw, receipt
    opener = build_opener(_NoRedirect)
    request = Request(url, headers={"Accept-Encoding": "identity", "User-Agent": "Spiderweb-AOI-Catalog/1.0"})
    with opener.open(request, timeout=30) as response:
        require(response.status == 200 and response.geturl() == url, "UNEXPECTED_SOURCE_RESPONSE")
        raw = response.read(MAX_CATALOG_BYTES + 1)
        require(len(raw) <= MAX_CATALOG_BYTES, "SOURCE_BYTE_LIMIT")
        length = response.headers.get("Content-Length")
        require(length is None or (length.isdigit() and int(length) == len(raw)), "TRUNCATED_SOURCE_RESPONSE")
        receipt = {"url": url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                   "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw),
                   "etag": response.headers.get("ETag"), "last_modified": response.headers.get("Last-Modified"),
                   "content_type": response.headers.get("Content-Type"), "http_status": response.status}
    write_once(path, raw); write_once(receipt_path, canonical_bytes(receipt))
    return raw, receipt


def freeze_catalog(spec: dict, work_dir: Path, root: Path) -> dict:
    """Fetch/reuse metadata only; build an immutable catalog and a registry proposal."""
    inputs, retrievals = {}, {}
    for kind, suffix in (("collection", "json"), ("items", "json"), ("urls", "txt")):
        inputs[kind], retrievals[kind] = acquire_metadata(spec[f"{kind}_url"], work_dir,
                                                        f"{kind}.raw.{suffix}", spec["approved_url_prefixes"])
    catalog, receipt = convert_snapshot(inputs["collection"], inputs["items"], inputs["urls"], spec)
    snapshot = digest({"spec": spec, "input_hashes": receipt["input_hashes"]})
    target = root / "registry" / "aoi" / "catalogs" / spec["dataset_id"] / snapshot
    require(target.resolve().is_relative_to(root.resolve()), "OUTPUT_OUTSIDE_ROOT")
    for kind, suffix in (("collection", "json"), ("items", "json"), ("urls", "txt")):
        write_once(target / f"{kind}.raw.{suffix}", inputs[kind])
    receipt["retrievals"] = retrievals
    receipt["source_spec"] = copy.deepcopy(spec)
    write_once(target / "manifest.json", canonical_bytes(receipt))
    write_once(target / "catalog.geojson", canonical_bytes(catalog))
    provider = {"provider_id": spec["provider_id"], "label": spec["label_raw"],
                "dataset_class": spec["dataset_class"], "catalog_type": "geojson",
                "catalog_path": str((target / "catalog.geojson").relative_to(root)),
                "catalog_sha256": receipt["catalog_sha256"], "catalog_record_count": len(catalog["features"]),
                "catalog_version": snapshot, "source_manifest_path": str((target / "manifest.json").relative_to(root)),
                "original_producer": spec["original_producer"], "publication_portal": "NOAA Digital Coast"}
    proposal = {"schema_version": "spiderweb.spatial_dataset_providers.v0.1", "providers": {spec["dataset_id"]: provider}}
    write_once(target / "registry-proposal.json", canonical_bytes(proposal))
    return proposal
