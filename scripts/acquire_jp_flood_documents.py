#!/usr/bin/env python3
"""Acquire JP municipal flood-document coverage with explicit source states.

Bounded model:
- 77 municipalities are listed in JP "Sectores en Zona Inundables".
- 76 listed PDFs are currently retrievable.
- Quebradillas is LISTED_BUT_MISSING (listed, linked PDF unavailable).
- Florida is NOT_LISTED in that source series.
- Quebradillas uses a hash-frozen local HMP manifestation for operational coverage.
- Florida may still use its authoritative remote HMP fallback.

Quebradillas remote HMP access is provenance-only because the upstream location may
return 403. Runtime use therefore verifies exact local bytes against the frozen
SHA256 and byte-size receipt and never silently downgrades to an unverified file.

The downloader is restart-friendly:
- completed remote files are reused only when local size matches remote Content-Length;
- incomplete downloads use .part files and are never promoted;
- size mismatch forces reacquisition;
- SHA256 is recorded for every acquired operational document.
"""
from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import os
import re
import shutil
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PORTAL_URL = "https://portaldeinundacion.jp.pr.gov/riesgo.html"
FLORIDA_HMP_URL = "https://jp.pr.gov/wp-content/uploads/2021/10/Flor-Plan-Approved-HMP.pdf"
QUEBRADILLAS_HMP_PROVENANCE_URL = (
    "https://jp.pr.gov/wp-content/uploads/2022/01/Queb-Approved-HMP.pdf"
)
QUEBRADILLAS_FROZEN_FILENAME = "Quebradillas.pdf"
QUEBRADILLAS_FROZEN_BYTE_SIZE = 51_199_142
QUEBRADILLAS_FROZEN_SHA256 = (
    "a1a2ccbfe0097da6f531e78f834d01be5a1555700b809d8f68b162db83d23e7a"
)

SOURCE_STATES = {"AVAILABLE", "LISTED_BUT_MISSING", "NOT_LISTED"}
EXPECTED_LISTED = 77
EXPECTED_AVAILABLE = 76
EXPECTED_MUNICIPALITIES = 78
UA = "spiderweb-pr-jp-flood-documents/2.1"

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
        self.href: str | None = None
        self.text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.href = href
                self.text = []

    def handle_data(self, data: str) -> None:
        if self.href is not None:
            self.text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.href is not None:
            self.links.append((self.href, " ".join(self.text).strip()))
            self.href = None
            self.text = []

def _encoded(url: str) -> str:
    return urllib.parse.quote(url, safe=":/?&=%")

def _request(url: str, *, method: str = "GET", timeout: int = 90):
    return urllib.request.urlopen(
        urllib.request.Request(_encoded(url), method=method, headers={"User-Agent": UA}),
        timeout=timeout,
    )

def fetch_bytes(url: str, timeout: int = 90) -> tuple[bytes, dict[str, str], str]:
    with _request(url, timeout=timeout) as response:
        return response.read(), dict(response.headers.items()), response.geturl()

def head_state(url: str, timeout: int = 60) -> tuple[int | None, dict[str, str]]:
    try:
        with _request(url, method="HEAD", timeout=timeout) as response:
            length = response.headers.get("Content-Length")
            return (int(length) if length else None), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        return None, {"_http_status": str(exc.code)}
    except Exception as exc:
        return None, {"_head_error": type(exc).__name__}

def discover_series(html_text: str, base_url: str = PORTAL_URL) -> list[dict[str, Any]]:
    parser = _Links()
    parser.feed(html_text)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for href, anchor_text in parser.links:
        if ".pdf" not in href.lower():
            continue
        source_url = urllib.parse.urljoin(base_url, href)
        if source_url in seen:
            continue
        seen.add(source_url)

        raw_label = re.sub(r"\s+", " ", anchor_text).strip()
        municipality = CANONICAL_BY_KEY.get(_key(raw_label))
        if municipality is None:
            filename = urllib.parse.unquote(
                urllib.parse.urlparse(source_url).path.rsplit("/", 1)[-1]
            )
            raw_name = re.sub(r"_sectores_inundables.*$", "", filename, flags=re.I)
            municipality = CANONICAL_BY_KEY.get(_key(raw_name.replace("_", " ")))

        rows.append(
            {
                "municipality": municipality,
                "municipality_raw": raw_label or None,
                "document_class": "flood_risk_zone_map",
                "source_series": "JP_SECTORES_EN_ZONA_INUNDABLES",
                "source_url": source_url,
                "source_url_raw_href": href,
                "source_state": "AVAILABLE",
                "authority": "Junta de Planificación de Puerto Rico",
                "equivalent_series_member": True,
            }
        )
    return rows

def apply_source_states(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_municipality = {row["municipality"]: row for row in rows}

    quebradillas = by_municipality.get("Quebradillas")
    if quebradillas is None:
        raise AssertionError("Quebradillas must remain listed in the 77-member source series")
    quebradillas.update(
        {
            "source_state": "LISTED_BUT_MISSING",
            "fallback_document_class": "hazard_mitigation_plan",
            "fallback_source_url": QUEBRADILLAS_HMP_PROVENANCE_URL,
            "fallback_source_access_state": "REMOTE_FORBIDDEN_OR_UNRELIABLE",
            "fallback_operational_mode": "frozen_local_manifestation",
            "fallback_relationship": "authoritative_fallback_not_equivalent",
            "frozen_manifestation": {
                "filename": QUEBRADILLAS_FROZEN_FILENAME,
                "byte_size": QUEBRADILLAS_FROZEN_BYTE_SIZE,
                "sha256": QUEBRADILLAS_FROZEN_SHA256,
                "identity_scope": "byte_manifestation",
            },
        }
    )

    rows.append(
        {
            "municipality": "Florida",
            "municipality_raw": "Florida",
            "document_class": None,
            "source_series": "JP_SECTORES_EN_ZONA_INUNDABLES",
            "source_url": None,
            "source_url_raw_href": None,
            "source_state": "NOT_LISTED",
            "authority": "Junta de Planificación de Puerto Rico",
            "equivalent_series_member": False,
            "fallback_document_class": "hazard_mitigation_plan",
            "fallback_source_url": FLORIDA_HMP_URL,
            "fallback_operational_mode": "remote_fetch",
            "fallback_relationship": "authoritative_fallback_not_equivalent",
        }
    )
    return rows

def validate(rows: list[dict[str, Any]]) -> None:
    assert len(rows) == EXPECTED_MUNICIPALITIES
    assert len({row["municipality"] for row in rows}) == EXPECTED_MUNICIPALITIES
    assert all(row["source_state"] in SOURCE_STATES for row in rows)
    assert sum(row["source_state"] != "NOT_LISTED" for row in rows) == EXPECTED_LISTED
    assert sum(row["source_state"] == "AVAILABLE" for row in rows) == EXPECTED_AVAILABLE
    assert sum(row["source_state"] == "LISTED_BUT_MISSING" for row in rows) == 1
    assert sum(row["source_state"] == "NOT_LISTED" for row in rows) == 1

    q = next(row for row in rows if row["municipality"] == "Quebradillas")
    f = next(row for row in rows if row["municipality"] == "Florida")
    assert q["source_state"] == "LISTED_BUT_MISSING"
    assert q["source_url"], "dead series URL must be preserved"
    assert q["fallback_operational_mode"] == "frozen_local_manifestation"
    assert q["frozen_manifestation"]["sha256"] == QUEBRADILLAS_FROZEN_SHA256
    assert q["frozen_manifestation"]["byte_size"] == QUEBRADILLAS_FROZEN_BYTE_SIZE
    assert f["source_state"] == "NOT_LISTED"
    assert f["source_url"] is None
    assert f["fallback_operational_mode"] == "remote_fetch"
    for row in (q, f):
        assert row["fallback_document_class"] == "hazard_mitigation_plan"
        assert row["fallback_relationship"] == "authoritative_fallback_not_equivalent"
        assert row["fallback_source_url"]

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def verify_frozen_quebradillas(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(
            f"QUEBRADILLAS_FROZEN_MISSING {path}; provide --quebradillas-fallback"
        )
    size = path.stat().st_size
    if size != QUEBRADILLAS_FROZEN_BYTE_SIZE:
        raise RuntimeError(
            f"QUEBRADILLAS_SIZE_MISMATCH expected={QUEBRADILLAS_FROZEN_BYTE_SIZE} got={size}"
        )
    digest = sha256_file(path)
    if digest != QUEBRADILLAS_FROZEN_SHA256:
        raise RuntimeError(
            f"QUEBRADILLAS_SHA256_MISMATCH expected={QUEBRADILLAS_FROZEN_SHA256} got={digest}"
        )
    return {
        "acquisition_status": "frozen_local_verified",
        "filename": path.name,
        "local_path": str(path),
        "byte_size": size,
        "sha256": digest,
        "verification": "BYTE_SIZE_AND_SHA256_PASS",
    }

def acquire_resume_safe(url: str, target: Path, timeout: int) -> dict[str, Any]:
    remote_size, head = head_state(url, timeout=min(timeout, 60))
    if target.is_file() and target.stat().st_size > 0 and remote_size is not None:
        if target.stat().st_size == remote_size:
            return {
                "acquisition_status": "reused_verified_size",
                "filename": target.name,
                "local_path": str(target),
                "byte_size": target.stat().st_size,
                "sha256": sha256_file(target),
                "remote_content_length": remote_size,
                "etag": head.get("ETag") or head.get("Etag"),
                "last_modified": head.get("Last-Modified"),
            }

    part = Path(str(target) + ".part")
    if part.exists():
        part.unlink()

    req = urllib.request.Request(_encoded(url), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as response, part.open("wb") as out:
        expected_header = response.headers.get("Content-Length")
        expected = int(expected_header) if expected_header else remote_size
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            out.write(block)
        final_url = response.geturl()
        response_headers = dict(response.headers.items())

    got = part.stat().st_size
    if got <= 0:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"ZERO_BYTE {target.name}")
    if expected is not None and got != expected:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"SIZE_MISMATCH {target.name}: expected={expected} got={got}")

    os.replace(part, target)
    return {
        "acquisition_status": "downloaded",
        "filename": target.name,
        "local_path": str(target),
        "byte_size": got,
        "sha256": sha256_file(target),
        "remote_content_length": expected,
        "final_url": final_url,
        "etag": response_headers.get("ETag") or response_headers.get("Etag"),
        "last_modified": response_headers.get("Last-Modified"),
        "content_type": response_headers.get("Content-Type"),
    }

def build_manifest(
    download: bool,
    out_dir: Path,
    timeout: int,
    quebradillas_fallback: Path | None = None,
) -> dict[str, Any]:
    portal_bytes, portal_headers, portal_final = fetch_bytes(PORTAL_URL, timeout)
    discovered = discover_series(portal_bytes.decode("utf-8", "ignore"), portal_final)
    if len(discovered) != EXPECTED_LISTED:
        raise AssertionError(f"expected {EXPECTED_LISTED} listed PDFs, got {len(discovered)}")

    rows = apply_source_states(discovered)
    validate(rows)

    if download:
        out_dir.mkdir(parents=True, exist_ok=True)
        for index, row in enumerate(sorted(rows, key=lambda r: _key(r["municipality"])), 1):
            print(
                f'[{index}/78] {row["municipality"]} '
                f'{row["source_state"]} -> '
                f'{row.get("fallback_document_class") or row.get("document_class")}'
            )

            if row["municipality"] == "Quebradillas":
                if quebradillas_fallback is None:
                    raise RuntimeError(
                        "Quebradillas requires --quebradillas-fallback pointing to the frozen PDF"
                    )
                verified = verify_frozen_quebradillas(quebradillas_fallback)
                target = out_dir / QUEBRADILLAS_FROZEN_FILENAME
                if quebradillas_fallback.resolve() != target.resolve():
                    shutil.copy2(quebradillas_fallback, target)
                    verified = verify_frozen_quebradillas(target)
                row["operational_document"] = verified
                continue

            if row["source_state"] == "NOT_LISTED":
                source_url = row["fallback_source_url"]
            else:
                source_url = row["source_url"]

            filename = urllib.parse.unquote(
                urllib.parse.urlparse(source_url).path.rsplit("/", 1)[-1]
            ) or f'{row["municipality"]}.pdf'
            row["operational_document"] = acquire_resume_safe(
                source_url, out_dir / filename, timeout
            )

    manifest = {
        "manifest_version": "2.1",
        "producer": "spiderweb-pr",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority": "Junta de Planificación de Puerto Rico",
        "portal_url": PORTAL_URL,
        "portal_final_url": portal_final,
        "portal_sha256": hashlib.sha256(portal_bytes).hexdigest(),
        "portal_etag": portal_headers.get("ETag") or portal_headers.get("Etag"),
        "portal_last_modified": portal_headers.get("Last-Modified"),
        "source_state_enum": sorted(SOURCE_STATES),
        "invariants": {
            "municipalities": 78,
            "series_listed": 77,
            "series_available": 76,
            "listed_but_missing": 1,
            "not_listed": 1,
            "authoritative_fallbacks": 2,
            "operational_coverage": 78,
            "quebradillas_frozen_sha256": QUEBRADILLAS_FROZEN_SHA256,
            "quebradillas_frozen_byte_size": QUEBRADILLAS_FROZEN_BYTE_SIZE,
        },
        "documents": sorted(rows, key=lambda row: _key(row["municipality"])),
    }
    return manifest

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/jp_flood_documents/manifest.json")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--out-dir", default="data/jp_flood_documents/raw")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--quebradillas-fallback",
        type=Path,
        default=None,
        help="Local frozen Quebradillas HMP; exact SHA256/size required.",
    )
    args = parser.parse_args()

    manifest = build_manifest(
        args.download,
        Path(args.out_dir),
        args.timeout,
        args.quebradillas_fallback,
    )
    path = Path(args.manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "JP_FLOOD_DOCUMENT_GATE = PASS "
        "(76 AVAILABLE + 1 LISTED_BUT_MISSING + 1 NOT_LISTED = 78; "
        "Quebradillas frozen bytes required)"
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
