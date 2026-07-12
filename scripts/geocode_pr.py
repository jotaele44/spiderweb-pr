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
import re
import ssl
import sys
import time
import unicodedata
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


def _within_pr(lat: float, lon: float) -> bool:
    """True if (lat, lon) falls inside the PR bounding box (incl. Mona, Vieques,
    Culebra). Used to reject provider results that geocoded to a same-named
    mainland street."""
    return PR_LAT[0] <= lat <= PR_LAT[1] and PR_LON[0] <= lon <= PR_LON[1]


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
    """Canonicalize before hashing so 'San Juan, PR', 'san juan,  pr', and
    'Bayamón'/'Bayamon' share a cache entry: lowercase, strip accents (NFKD +
    drop combining marks, so 'ñ'→'n'), drop punctuation, collapse whitespace.
    Empty/None → ''.

    NOTE: backends always receive the ORIGINAL address string, so this governs
    only cache-key dedup and the FixtureBackend lookup — it never alters what
    we send to a provider."""
    if not address:
        return ""
    text = unicodedata.normalize("NFKD", address)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(text.split())


def _addr_key(address: str) -> str:
    return hashlib.sha256(_norm_address(address).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- backends

class Backend:
    """Subclass and implement ``geocode``. Stateless by convention; per-call."""

    name: str = "abstract"

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        # Explicit extension-point guard. ``Backend`` is the abstract provider
        # interface; a concrete backend (Census / Nominatim / Google / Fixture)
        # owns the actual geocoding. Offline-only deployments should use
        # ``FixtureBackend`` or lean on ``CachedBackend``'s on-disk cache rather
        # than a live provider. A subclass that forgets to implement geocode()
        # fails loudly here — naming itself — instead of raising a bare,
        # message-less NotImplementedError.
        raise NotImplementedError(
            f"{type(self).__name__} must implement geocode(address) -> "
            f"Optional[GeocodeResult]; Backend is the abstract provider "
            f"interface (see CensusBackend / NominatimBackend / FixtureBackend)."
        )


def _is_offline() -> bool:
    return os.environ.get("SPIDERWEB_OFFLINE") == "1"


class GeocodeBackendError(Exception):
    """A transport-level failure (timeout, HTTP 4xx/5xx, DNS, TLS, bad JSON).

    Kept DISTINCT from a clean 'no match' (a 200 with zero results, which a
    backend signals by returning None). The cache layer must never persist a
    negative marker for a transient error, or one flaky request poisons an
    address permanently (NEG_TTL_SECS defaults to 0)."""


def _http_get_json(url: str, *, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
    """One-shot urllib GET → JSON.

    Returns None ONLY when offline (a deliberate skip). On any transport/parse
    failure it raises :class:`GeocodeBackendError` so the caller can tell a
    transient error apart from a genuine empty result."""
    if _is_offline():
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            payload = resp.read()
        return json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise GeocodeBackendError(f"{type(exc).__name__}: {exc}") from exc


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
            # Census /onelineaddress returns TIGER street-line interpolation;
            # 'tigerLine.side' is the L/R side flag, NOT a match-quality signal,
            # so report the honest interpolation confidence instead.
            confidence="interpolated",
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

    def _negative_expired(self, entry: Dict[str, Any]) -> bool:
        """A negative entry is reconsidered once it is older than NEG_TTL_SECS.
        With the default (0) negatives are permanent and this is always False."""
        if self.NEG_TTL_SECS <= 0:
            return False
        ts = entry.get("ts")
        if not isinstance(ts, (int, float)):
            return False
        return (time.time() - ts) > self.NEG_TTL_SECS

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        if not address or not address.strip():
            return None
        path = self._cache_path(address)
        cached = self._load(path)
        if cached is not None:
            if cached.get("negative"):
                if not self._negative_expired(cached):
                    return None
                # expired negative → fall through and re-attempt
            else:
                try:
                    # The cache file always carries the ORIGINAL method tag so
                    # downstream callers know which backend produced the result.
                    result = GeocodeResult(
                        lat=float(cached["lat"]),
                        lon=float(cached["lon"]),
                        method=cached["method"],
                        confidence=cached.get("confidence", "unknown"),
                        matched_address=cached.get("matched_address", address),
                    )
                except (KeyError, TypeError, ValueError):
                    result = None
                # Serve only an in-PR cached point; a malformed or out-of-PR
                # entry (e.g. an older poisoned cache) falls through to refetch.
                if result is not None and _within_pr(result.lat, result.lon):
                    return result

        errored = False
        for backend in self.backends:
            try:
                result = backend.geocode(address)
            except GeocodeBackendError:
                # Transient transport failure — NOT a no-match. Skip this
                # backend but remember it so we don't write a negative marker.
                errored = True
                continue
            if result is None:
                continue
            if not _within_pr(result.lat, result.lon):
                # Provider returned a non-PR coordinate (ambiguous mainland
                # street name); reject rather than cache a wrong point.
                continue
            self._store(path, result.as_dict())
            return result

        # Negative-cache only a genuine, fully-attempted all-miss: online AND no
        # backend errored (a transient failure must be retried on the next run).
        if not _is_offline() and not errored:
            self._store(path, {"negative": True, "address": address, "ts": time.time()})
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


# Keyed by RESOLVED path so a second call with a different municipios_path
# loads that file instead of silently returning the first dataset.
_MUNICIPIOS_CACHE: Dict[Path, List[Tuple[str, Dict[str, Any]]]] = {}


def _load_municipios(path: Path = DEFAULT_MUNICIPIOS) -> List[Tuple[str, Dict[str, Any]]]:
    key = path.resolve()
    cached = _MUNICIPIOS_CACHE.get(key)
    if cached is not None:
        return cached
    if not path.exists():
        _MUNICIPIOS_CACHE[key] = []
        return _MUNICIPIOS_CACHE[key]
    fc = json.loads(path.read_text(encoding="utf-8"))
    out: List[Tuple[str, Dict[str, Any]]] = []
    for f in fc.get("features", []):
        name = ((f.get("properties") or {}).get("NAME") or "").strip()
        geom = f.get("geometry") or {}
        if name and geom:
            out.append((name, geom))
    _MUNICIPIOS_CACHE[key] = out
    return out


def municipio_from_point(lat: float, lon: float, *, municipios_path: Path = DEFAULT_MUNICIPIOS) -> str:
    """PIP a (lat, lon) into a PR municipio. Returns the NAME field, or "" if
    outside any municipio polygon (including out-of-PR points)."""
    if not _within_pr(lat, lon):
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
