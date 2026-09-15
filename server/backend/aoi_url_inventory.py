"""Classify every published URL-list row without dropping metadata or unknowns.

DATA identity is exact membership in the STAC asset URL set, not filename
similarity. Auxiliary declarations are exact URL/evidence bindings; suffixes
are never sufficient to remove an entry from the acquisition denominator.
"""
from __future__ import annotations

from collections import Counter
from typing import Callable
from urllib.parse import urlsplit

STATES = ("DATA", "ITEM_METADATA", "CATALOG_METADATA", "DECLARED_AUXILIARY", "BLANK", "UNRESOLVED")
AUXILIARY_ROLES = frozenset({"metadata", "tile_index", "virtual_raster", "file_inventory"})


class UrlInventoryError(ValueError):
    """A failed audit retains all rows and set differences for adjudication."""

    def __init__(self, report: dict):
        super().__init__("URL_INVENTORY_NOT_CLOSED")
        self.report = report


def _sets(a: list[str], b: list[str]) -> dict:
    left, right = set(a), set(b)
    return {"INTERSECTION": sorted(left & right), "A_ONLY": sorted(left - right),
            "B_ONLY": sorted(right - left), "UNION": sorted(left | right),
            "SYMMETRIC_DIFFERENCE": sorted(left ^ right)}


def audit_url_inventory(raw: bytes, *, data_urls: list[str], item_urls: list[str],
                        structural_urls: list[str], auxiliary_bindings: list[dict],
                        approve: Callable[[str], str],
                        data_suffixes: tuple[str, ...] = (".tif", ".tiff")) -> dict:
    """Return a closed inventory or raise an error containing the complete audit.

    A URL-list entry can be data, an exact linked STAC item, an explicitly
    configured catalog, or an exact declared auxiliary URL. Unknown, duplicate,
    ambiguous and unsafe entries never disappear. Only DATA entries must equal
    the independent STAC data-asset set; metadata remains separately accounted.
    """
    groups = {"DATA": list(data_urls), "ITEM_METADATA": list(item_urls),
              "CATALOG_METADATA": list(structural_urls), "DECLARED_AUXILIARY": []}
    declarations: dict[str, dict] = {}
    declaration_errors = []
    if not isinstance(auxiliary_bindings, list):
        raise ValueError("INVALID_AUXILIARY_BINDINGS")
    for index, binding in enumerate(auxiliary_bindings):
        if not isinstance(binding, dict):
            declaration_errors.append(f"INVALID_AUXILIARY_BINDING:{index}")
            continue
        url, evidence = binding.get("url"), binding.get("evidence_url")
        try:
            approve(url)
            if urlsplit(url).path.lower().endswith(data_suffixes):
                raise ValueError("DATA_SUFFIX_CANNOT_BE_DECLARED_AUXILIARY")
            parsed = urlsplit(evidence) if isinstance(evidence, str) else None
            if (binding.get("role") not in AUXILIARY_ROLES or not parsed or parsed.scheme != "https"
                    or not parsed.hostname or parsed.username or parsed.password
                    or not isinstance(binding.get("basis"), str) or not binding["basis"].strip()):
                raise ValueError("AUXILIARY_EVIDENCE_UNBOUND")
            if url in declarations:
                raise ValueError("DUPLICATE_AUXILIARY_DECLARATION")
            declarations[url] = dict(binding)
            groups["DECLARED_AUXILIARY"].append(url)
        except (ValueError, TypeError, AttributeError) as error:
            declaration_errors.append(f"AUXILIARY:{index}:{error}")
    memberships: dict[str, list[str]] = {}
    for category, urls in groups.items():
        for url in urls:
            approve(url)
            memberships.setdefault(url, []).append(category)
    duplicate_bindings = {url: categories for url, categories in memberships.items()
                          if len(categories) != 1}
    # Decode only as UTF-8; preserve text and line endings in each raw_line.
    text = raw.decode("utf-8-sig", errors="strict")
    lines = text.splitlines(keepends=True)
    rows = []
    for number, raw_line in enumerate(lines, start=1):
        value = raw_line.rstrip("\r\n")
        row = {"line_number": number, "raw_line": raw_line, "url_raw": value,
               "state": "UNRESOLVED", "reasons": [], "binding": None}
        rows.append(row)
        if value == "":
            row["state"] = "BLANK"
            continue
        try:
            approve(value)
        except (ValueError, TypeError, AttributeError) as error:
            row["reasons"].append(str(error))
            continue
        categories = memberships.get(value, [])
        if len(categories) == 1:
            row["state"] = categories[0]
            if categories[0] == "DECLARED_AUXILIARY":
                row["binding"] = declarations[value]
        elif categories:
            row["reasons"].append("AMBIGUOUS_URL_ROLE_BINDING")
        else:
            row["reasons"].append("URL_NOT_BOUND_TO_STAC_OR_DECLARED_AUXILIARY")
    frequencies = Counter(row["url_raw"] for row in rows if row["state"] != "BLANK")
    duplicates = {url: n for url, n in frequencies.items() if n > 1}
    for row in rows:
        if row["url_raw"] in duplicates:
            row["state"] = "UNRESOLVED"
            row["reasons"].append("DUPLICATE_URL_LIST_ENTRY")
    # Retain candidates before role filtering as well as accepted data URLs.
    data_set = set(data_urls)
    listed_data = []
    for row in rows:
        value = row["url_raw"]
        try:
            approve(value)
        except (ValueError, TypeError, AttributeError):
            continue
        # Suffix discovers additional candidates for the difference report only;
        # it never promotes an unbound row into DATA or an acquisition plan.
        if value in data_set or urlsplit(value).path.lower().endswith(data_suffixes):
            listed_data.append(value)
    data_relation = _sets(data_urls, listed_data)
    observed_metadata = [row["url_raw"] for row in rows if row["state"] == "ITEM_METADATA"]
    states = {state: sum(row["state"] == state for row in rows) for state in STATES}
    blockers = list(declaration_errors)
    if duplicate_bindings:
        blockers.append("DUPLICATE_OR_AMBIGUOUS_EXPECTED_URL_BINDINGS")
    if duplicates:
        blockers.append("DUPLICATE_URL_LIST_ENTRY")
    if not data_urls or Counter(data_urls) != Counter(listed_data):
        blockers.append("STAC_DATA_URL_MULTISET_MISMATCH_OR_EMPTY")
    if states["UNRESOLVED"]:
        blockers.append("UNRESOLVED_URL_ROWS")
    report = {"schema_version": "aoi_url_inventory.v1.0", "rows": rows,
              "input_has_utf8_bom": raw.startswith(b"\xef\xbb\xbf"),
              "counts": {"lines": len(rows), **states},
              "duplicate_urls": duplicates, "ambiguous_bindings": duplicate_bindings,
              "data_url_relation": data_relation,
              "item_metadata_relation": _sets(item_urls, observed_metadata),
              "item_metadata_list_presence_required": False,
              "blockers": blockers, "arithmetic_closed": sum(states.values()) == len(rows),
              "state": "BLOCKED" if blockers else "PASS"}
    if blockers:
        raise UrlInventoryError(report)
    return report
