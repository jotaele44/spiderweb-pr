#!/usr/bin/env python3
"""
PR address → (lat, lon, municipio) helper for non-direct-coord harvesters.

WHY THIS EXISTS
---------------
NamUs and IOM Missing Migrants carry last-seen lat/lon. Every other source we
ingest (PRPB Alertas, Observatorio PDFs, journalism, FB tip-stream) carries
*address text only*. Without geocoding, those sources never produce points and
never reach the spatial layer — the whole point of the federation is lost.

This module:

  1. Defines a small backend interface so we can swap providers without
     touching harvester code (``Backend.geocode(address) -> GeocodeResult``).
  2. Ships three backends — Census (free, supports PR), Nominatim (free, OSM),
     Google (paid, env-gated) — and a FixtureBackend for tests.
  3. Wraps any backend in a file-system cache (``data/sources/_geocode_cache/``)
     so repeat harvests don't re-hit the network.
  4. Provides ``municipio_from_point(lat, lon)`` that runs the same PIP
     against ``data/municipios.geojson`` the populate step does.

Stdlib only (urllib + json + hashlib + pathlib + ssl). No third-party deps.

OPERATOR NOTES
--------------
* The cache is content-addressed (sha256 of the normalized address). Same
  address always yields the same cache file, regardless of which backend
  produced it. The backend identity is recorded in the cache entry as
  ``method``.
* A cache *miss* in offline mode returns ``None`` rather than raising — so
  harvesters degrade gracefully (row keeps its address, just no coordinates).
* Set ``SPIDERWEB_OFFLINE=1`` to skip all network calls (tests, CI).
* For the Google backend, set ``SPIDERWEB_GOOGLE_GEOCODER_KEY=…``. Otherwise
  the backend's ``geocode`` returns ``None`` immediately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = REPO_ROOT / "data" / "sources" / "_geocode_cache"
DEFAULT_MUNICIPIOS = REPO_ROOT / "data" / "municipios.geojson"

PR_LAT = (17.6, 18.7)
PR_LON = (-68.0, -65.1)

USER_AGENT = "spiderweb-pr/geocode (https://github.com/; missing-persons pipeline)"


# ---------------------------------------------------------------- result type

@dataclass(frozen=True)
class GeocodeResult:
    lat: float
    lon: float
    method: str          # "census" | "nominatim" | "google" | "fixture" | "cache"
    confidence: str      # backend-specific: "exact" | "approximate" | "interpolated" | "unknown"
    matched_address: str  # what the backend thought the address actually was

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _norm_address(address: str) -> str:
    """Canonicalize before hashing so 'San Juan, PR' and 'san juan,  pr' share
    a cache entry. Lowercase, collapse whitespace, strip punctuation runs."""
    return " ".join(address.lower().replace(",", " ").split())


def _addr_key(address: str) -> str:
    return hashlib.sha256(_norm_address(address).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- backends

class Backend:
    """Subclass and implement ``geocode``. Stateless by convention; per-call."""

    name: str = "abstract"

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        raise NotImplementedError


def _is_offline() -> bool:
    return os.environ.get("SPIDERWEB_OFFLINE") == "1"


def _http_get_json(url: str, *, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
    """One-shot urllib GET → JSON. Returns None on any failure (no exceptions
    propagate to caller — harvester resilience matters more than diagnostics
    here; backend ``method`` tag tells you which backend was tried)."""
    if _is_offline():
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            payload = resp.read()
        return json.loads(payload.decode("utf-8"))
    except Exception:
        return None


class CensusBackend(Backend):
    """US Census Geocoder. Free, no key, supports PR. ~10k req/day soft cap.
    Reference: https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.pdf
    """

    name = "census"
    URL_TMPL = (
        "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
        "?address={addr}&benchmark=Public_AR_Current&format=json"
    )

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        url = self.URL_TMPL.format(addr=urllib.parse.quote_plus(address))
        data = _http_get_json(url)
        if not data:
            return None
        matches = (data.get("result") or {}).get("addressMatches") or []
        if not matches:
            return None
        m = matches[0]
        coords = m.get("coordinates") or {}
        try:
            lat = float(coords["y"])
            lon = float(coords["x"])
        except (KeyError, TypeError, ValueError):
            return None
        return GeocodeResult(
            lat=round(lat, 6),
            lon=round(lon, 6),
            method=self.name,
            confidence=str(m.get("tigerLine", {}).get("side") or "approximate"),
            matched_address=m.get("matchedAddress") or address,
        )


class NominatimBackend(Backend):
    """OpenStreetMap Nominatim. Free, OSM-backed. Strict 1 req/sec policy and
    explicit User-Agent required. Caller is responsible for rate limiting.
    Reference: https://operations.osmfoundation.org/policies/nominatim/
    """

    name = "nominatim"
    URL_TMPL = "https://nominatim.openstreetmap.org/search?q={addr}&format=json&limit=1&countrycodes=pr"

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        url = self.URL_TMPL.format(addr=urllib.parse.quote_plus(address))
        data = _http_get_json(url)
        if not isinstance(data, list) or not data:
            return None
        m = data[0]
        try:
            lat = float(m["lat"])
            lon = float(m["lon"])
        except (KeyError, TypeError, ValueError):
            return None
        return GeocodeResult(
            lat=round(lat, 6),
            lon=round(lon, 6),
            method=self.name,
            confidence=m.get("type", "unknown"),
            matched_address=m.get("display_name", address),
        )


class GoogleBackend(Backend):
    """Google Maps Geocoding API. Requires SPIDERWEB_GOOGLE_GEOCODER_KEY env
    var. Paid (free tier ~$200/mo as of 2024). Highest accuracy for PR
    addresses with informal/Spanish-language formats."""

    name = "google"
    URL_TMPL = "https://maps.googleapis.com/maps/api/geocode/json?address={addr}&region=pr&key={key}"

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        key = os.environ.get("SPIDERWEB_GOOGLE_GEOCODER_KEY")
        if not key:
            return None
        url = self.URL_TMPL.format(addr=urllib.parse.quote_plus(address), key=key)
        data = _http_get_json(url)
        if not data or data.get("status") != "OK":
            return None
        results = data.get("results") or []
        if not results:
            return None
        r = results[0]
        try:
            lat = float(r["geometry"]["location"]["lat"])
            lon = float(r["geometry"]["location"]["lng"])
        except (KeyError, TypeError, ValueError):
            return None
        return GeocodeResult(
            lat=round(lat, 6),
            lon=round(lon, 6),
            method=self.name,
            confidence=r.get("geometry", {}).get("location_type", "unknown"),
            matched_address=r.get("formatted_address", address),
        )


class FixtureBackend(Backend):
    """Tests-only. Returns a pre-canned result if the *normalized* address
    matches a key in ``responses``. Otherwise returns None."""

    name = "fixture"

    def __init__(self, responses: Dict[str, GeocodeResult]) -> None:
        self.responses = {_norm_address(k): v for k, v in responses.items()}

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        return self.responses.get(_norm_address(address))


# ---------------------------------------------------------------- cache wrapper

class CachedBackend(Backend):
    """Wraps a list of backends. On geocode():
        1. Cache hit → return cached GeocodeResult (method tagged "cache").
        2. Cache miss → try each inner backend in order; first hit wins, cached.
        3. All miss → write a "negative" marker so we don't re-query next time.
    """

    name = "cached"
    NEG_TTL_SECS = 0  # negative cache is permanent until the cache dir is wiped

    def __init__(self, backends: List[Backend], cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
        self.backends = backends
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, address: str) -> Path:
        return self.cache_dir / f"{_addr_key(address)}.json"

    def _load(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _store(self, path: Path, payload: Dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        path = self._cache_path(address)
        cached = self._load(path)
        if cached is not None:
            if cached.get("negative"):
                return None
            try:
                # The cache file always carries the ORIGINAL method tag so
                # downstream callers know which backend produced the result.
                return GeocodeResult(
                    lat=float(cached["lat"]),
                    lon=float(cached["lon"]),
                    method=cached["method"],
                    confidence=cached.get("confidence", "unknown"),
                    matched_address=cached.get("matched_address", address),
                )
            except (KeyError, TypeError, ValueError):
                pass  # malformed cache entry — fall through to refetch

        for backend in self.backends:
            result = backend.geocode(address)
            if result is None:
                continue
            self._store(path, result.as_dict())
            return result

        # Negative cache only if we actually attempted (not offline).
        if not _is_offline():
            self._store(path, {"negative": True, "address": address})
        return None


# ---------------------------------------------------------------- municipio PIP

def _ring_contains(point: Tuple[float, float], ring: List[Tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-18) + xi):
            inside = not inside
        j = i
    return inside


def _polygon_contains(point: Tuple[float, float], geometry: Dict[str, Any]) -> bool:
    gtype = geometry.get("type")
    if gtype == "Polygon":
        rings = geometry.get("coordinates") or []
        if not rings:
            return False
        outer = [(c[0], c[1]) for c in rings[0]]
        if not _ring_contains(point, outer):
            return False
        for hole in rings[1:]:
            if _ring_contains(point, [(c[0], c[1]) for c in hole]):
                return False
        return True
    if gtype == "MultiPolygon":
        for poly in geometry.get("coordinates") or []:
            if not poly:
                continue
            outer = [(c[0], c[1]) for c in poly[0]]
            if not _ring_contains(point, outer):
                continue
            if any(_ring_contains(point, [(c[0], c[1]) for c in hole]) for hole in poly[1:]):
                continue
            return True
    return False


_MUNICIPIOS_CACHE: Optional[List[Tuple[str, Dict[str, Any]]]] = None


def _load_municipios(path: Path = DEFAULT_MUNICIPIOS) -> List[Tuple[str, Dict[str, Any]]]:
    global _MUNICIPIOS_CACHE
    if _MUNICIPIOS_CACHE is not None:
        return _MUNICIPIOS_CACHE
    if not path.exists():
        _MUNICIPIOS_CACHE = []
        return _MUNICIPIOS_CACHE
    fc = json.loads(path.read_text(encoding="utf-8"))
    out: List[Tuple[str, Dict[str, Any]]] = []
    for f in fc.get("features", []):
        name = ((f.get("properties") or {}).get("NAME") or "").strip()
        geom = f.get("geometry") or {}
        if name and geom:
            out.append((name, geom))
    _MUNICIPIOS_CACHE = out
    return out


def municipio_from_point(lat: float, lon: float, *, municipios_path: Path = DEFAULT_MUNICIPIOS) -> str:
    """PIP a (lat, lon) into a PR municipio. Returns the NAME field, or "" if
    outside any municipio polygon (including out-of-PR points)."""
    if not (PR_LAT[0] <= lat <= PR_LAT[1] and PR_LON[0] <= lon <= PR_LON[1]):
        return ""
    point = (lon, lat)  # GeoJSON is (lon, lat)
    for name, geom in _load_municipios(municipios_path):
        if _polygon_contains(point, geom):
            return name
    return ""


# ---------------------------------------------------------------- default stack

def default_backend(cache_dir: Path = DEFAULT_CACHE_DIR) -> CachedBackend:
    """The standard production stack: Census first (best PR coverage among
    free options), Nominatim as fallback, Google last if a key is set."""
    return CachedBackend(
        backends=[CensusBackend(), NominatimBackend(), GoogleBackend()],
        cache_dir=cache_dir,
    )


# ---------------------------------------------------------------- CLI

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Geocode a PR address. Useful for one-off ops checks."
    )
    parser.add_argument("address", help="Address to geocode.")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    args = parser.parse_args(argv)

    backend = default_backend(args.cache_dir)
    result = backend.geocode(args.address)
    if result is None:
        print(f"NO_MATCH (offline={int(_is_offline())})", file=sys.stderr)
        return 2
    muni = municipio_from_point(result.lat, result.lon)
    print(json.dumps({**result.as_dict(), "municipio": muni}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
