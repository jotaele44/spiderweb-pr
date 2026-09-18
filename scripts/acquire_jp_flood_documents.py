#!/usr/bin/env python3
"""Acquire Puerto Rico Planning Board municipal flood-document corpus.

Bounded source model:
- 77 live "Sectores en Zona Inundables" municipal PDFs discovered from the JP portal.
- Florida is not relabeled as a member of that series. It is wired into the same
  78-municipality lookup as an authoritative alternate document:
  "Plan de Mitigación contra Peligros Naturales".

The manifest therefore closes municipal document coverage at 78 while preserving:
  source_series_count == 77
  alternative_count == 1
  total_municipality_count == 78
"""
from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PORTAL_URL = "https://portaldeinundacion.jp.pr.gov/riesgo.html"
FLORIDA_URL = "https://jp.pr.gov/wp-content/uploads/2021/10/Flor-Plan-Approved-HMP.pdf"
EXPECTED_SERIES_COUNT = 77
EXPECTED_MUNICIPALITY_COUNT = 78
UA = "spiderweb-pr-jp-flood-documents/1.0"

CANONICAL_MUNICIPALITIES = (
    "Adjuntas","Aguada","Aguadilla","Aguas Buenas","Aibonito","Añasco","Arecibo","Arroyo",
    "Barceloneta","Barranquitas","Bayamón","Cabo Rojo","Caguas","Camuy","Canóvanas",
    "Carolina","Cataño","Cayey","Ceiba","Ciales","Cidra","Coamo","Comerío","Corozal",
    "Culebra","Dorado","Fajardo","Florida","Guánica","Guayama","Guayanilla","Guaynabo",
    "Gurabo","Hatillo","Hormigueros","Humacao","Isabela","Jayuya","Juana Díaz","Juncos",
    "Lajas","Lares","Las Marías","Las Piedras","Loíza","Luquillo","Manatí","Maricao",
    "Maunabo","Mayagüez","Moca","Morovis","Naguabo","Naranjito","Orocovis","Patillas",
    "Peñuelas","Ponce","Quebradillas","Rincón","Río Grande","Sabana Grande","Salinas",
    "San Germán","San Juan","San Lorenzo","San Sebastián","Santa Isabel","Toa Alta",
    "Toa Baja","Trujillo Alto","Utuado","Vega Alta","Vega Baja","Vieques","Villalba",
    "Yabucoa","Yauco",
)


def _key(value: str) -> str:
    s = unicodedata.normalize("NFKD", value)
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().strip()


CANONICAL_BY_KEY = {_key(x): x for x in CANONICAL_MUNICIPALITIES}


class _Links(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.current_href = href
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.current_href is not None:
            self.links.append((self.current_href, " ".join(self.current_text).strip()))
            self.current_href = None
            self.current_text = []


def fetch_bytes(url: str, timeout: int = 90) -> tuple[bytes, dict[str, str], str]:
    encoded = urllib.parse.quote(url, safe=":/?&=%")
    req = urllib.request.Request(encoded, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), dict(r.headers.items()), r.geturl()


def discover_series(html_text: str, base_url: str = PORTAL_URL) -> list[dict[str, Any]]:
    p = _Links()
    p.feed(html_text)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for href, anchor_text in p.links:
        if ".pdf" not in href.lower():
            continue
        url = urllib.parse.urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)

        label = re.sub(r"\s+", " ", anchor_text).strip()
        municipality = CANONICAL_BY_KEY.get(_key(label))
        if municipality is None:
            # Fallback only for discovery; canonical binding still has to close.
            filename = urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit("/", 1)[-1])
            raw = re.sub(r"_sectores_inundables.*$", "", filename, flags=re.I)
            municipality = CANONICAL_BY_KEY.get(_key(raw.replace("_", " ")))

        rows.append({
            "municipality": municipality,
            "municipality_raw": label or None,
            "document_class": "flood_risk_zone_map",
            "source_series": "JP_SECTORES_EN_ZONA_INUNDABLES",
            "equivalent_series_member": True,
            "source_url": url,
            "source_url_raw_href": href,
            "authority": "Junta de Planificación de Puerto Rico",
        })
    return rows


def validate(rows: list[dict[str, Any]]) -> None:
    series = [r for r in rows if r["document_class"] == "flood_risk_zone_map"]
    alt = [r for r in rows if r["document_class"] == "hazard_mitigation_plan"]

    assert len(series) == EXPECTED_SERIES_COUNT, (
        f"source-series denominator mismatch: expected {EXPECTED_SERIES_COUNT}, got {len(series)}"
    )
    assert len(alt) == 1, f"expected exactly one alternate document, got {len(alt)}"
    assert alt[0]["municipality"] == "Florida"
    assert alt[0]["equivalent_series_member"] is False
    assert not any(r["municipality"] == "Florida" for r in series), (
        "Florida must not be silently promoted into the 77-map source series"
    )

    names = [r["municipality"] for r in rows]
    assert None not in names, "unbound municipality remains"
    assert len(names) == EXPECTED_MUNICIPALITY_COUNT
    assert len(set(names)) == EXPECTED_MUNICIPALITY_COUNT, "duplicate municipality binding"
    assert set(names) == set(CANONICAL_MUNICIPALITIES), (
        "78-municipality coverage does not close exactly"
    )


def download_row(row: dict[str, Any], out_dir: Path, timeout: int) -> None:
    data, headers, final_url = fetch_bytes(row["source_url"], timeout=timeout)
    filename = urllib.parse.unquote(
        urllib.parse.urlparse(final_url).path.rsplit("/", 1)[-1]
    ) or f'{row["municipality"]}.pdf'
    target = out_dir / filename
    target.write_bytes(data)
    row.update({
        "final_url": final_url,
        "filename": filename,
        "local_path": str(target),
        "byte_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "etag": headers.get("ETag") or headers.get("Etag"),
        "last_modified": headers.get("Last-Modified"),
        "content_type": headers.get("Content-Type"),
        "acquisition_status": "downloaded",
    })


def build_manifest(download: bool, out_dir: Path, timeout: int) -> dict[str, Any]:
    portal_bytes, portal_headers, portal_final = fetch_bytes(PORTAL_URL, timeout=timeout)
    portal_html = portal_bytes.decode("utf-8", "ignore")
    rows = discover_series(portal_html, portal_final)

    rows.append({
        "municipality": "Florida",
        "municipality_raw": "Florida",
        "document_class": "hazard_mitigation_plan",
        "source_series": "JP_FLORIDA_HAZARD_MITIGATION_PLAN",
        "equivalent_series_member": False,
        "source_url": FLORIDA_URL,
        "source_url_raw_href": None,
        "authority": "Junta de Planificación de Puerto Rico",
        "relationship_to_series": "authoritative_alternate_not_equivalent",
        "series_absence_state": "outside_source_series_provisional",
    })

    validate(rows)

    if download:
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, row in enumerate(rows, 1):
            print(f'[{i}/{len(rows)}] {row["municipality"]}: {row["document_class"]}')
            download_row(row, out_dir, timeout)

    return {
        "manifest_version": "1.0",
        "producer": "spiderweb-pr",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority": "Junta de Planificación de Puerto Rico",
        "portal_url": PORTAL_URL,
        "portal_final_url": portal_final,
        "portal_sha256": hashlib.sha256(portal_bytes).hexdigest(),
        "portal_etag": portal_headers.get("ETag") or portal_headers.get("Etag"),
        "portal_last_modified": portal_headers.get("Last-Modified"),
        "invariants": {
            "puerto_rico_municipalities": EXPECTED_MUNICIPALITY_COUNT,
            "flood_risk_zone_map_series": EXPECTED_SERIES_COUNT,
            "authoritative_alternates": 1,
            "total_document_bindings": EXPECTED_MUNICIPALITY_COUNT,
            "florida_equivalent_series_member": False,
        },
        "documents": sorted(rows, key=lambda r: _key(r["municipality"])),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="data/jp_flood_documents/manifest.json")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--out-dir", default="data/jp_flood_documents/raw")
    ap.add_argument("--timeout", type=int, default=90)
    args = ap.parse_args()

    manifest = build_manifest(args.download, Path(args.out_dir), args.timeout)
    path = Path(args.manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    inv = manifest["invariants"]
    print(
        "JP_FLOOD_DOCUMENT_GATE = PASS "
        f'({inv["flood_risk_zone_map_series"]} series + '
        f'{inv["authoritative_alternates"]} alternate = '
        f'{inv["total_document_bindings"]} municipalities)'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
