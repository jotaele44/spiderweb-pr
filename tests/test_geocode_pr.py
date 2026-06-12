"""
Tests for scripts/geocode_pr.py — the address→(lat,lon,municipio) helper.

Pins the 2026-06-12 review's MEDIUM finding: the module was entirely untested,
and its subtlest branch is CachedBackend's negative-cache write — an OFFLINE
all-miss must NOT persist a negative marker (which is permanent,
NEG_TTL_SECS=0), or it would silently poison an address to no-geocode forever.

All tests run offline-safe: FixtureBackend is a pure dict lookup, and the only
network-touching path is explicitly exercised via the offline guard.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.geocode_pr import (  # noqa: E402
    CachedBackend,
    FixtureBackend,
    GeocodeResult,
    _addr_key,
    municipio_from_point,
)


@pytest.fixture(autouse=True)
def _deterministic_seed():
    yield


@pytest.fixture(autouse=True)
def _force_online(monkeypatch):
    """Default every test to ONLINE (SPIDERWEB_OFFLINE unset) so the negative-
    cache branch is exercised; the offline test re-sets it explicitly."""
    monkeypatch.delenv("SPIDERWEB_OFFLINE", raising=False)
    yield


class CountingFixtureBackend(FixtureBackend):
    """FixtureBackend that records how many times geocode() was called, so we
    can prove the cache actually short-circuits backend calls."""

    def __init__(self, responses):
        super().__init__(responses)
        self.calls = 0

    def geocode(self, address):
        self.calls += 1
        return super().geocode(address)


SJU = GeocodeResult(18.4222, -66.0691, "fixture", "exact", "San Juan, PR")


# ---------------------------------------------------------------- cache roundtrip

def test_miss_then_store_then_cache_hit(tmp_path: Path):
    backend = CountingFixtureBackend({"Plaza Las Americas, San Juan": SJU})
    cb = CachedBackend([backend], cache_dir=tmp_path)

    # First call: cache miss → backend hit → result stored.
    r1 = cb.geocode("Plaza Las Americas, San Juan")
    assert r1 is not None and r1.lat == 18.4222
    assert backend.calls == 1
    cache_file = tmp_path / f"{_addr_key('Plaza Las Americas, San Juan')}.json"
    assert cache_file.exists(), "positive result was not cached"

    # Second call: cache hit → backend NOT called again.
    r2 = cb.geocode("Plaza Las Americas, San Juan")
    assert r2 is not None and r2.lat == 18.4222
    assert backend.calls == 1, "cache hit should not re-invoke the backend"
    # Cached result preserves the original method tag.
    assert r2.method == "fixture"


def test_cache_key_is_normalized(tmp_path: Path):
    backend = CountingFixtureBackend({"Old San Juan, PR": SJU})
    cb = CachedBackend([backend], cache_dir=tmp_path)
    assert cb.geocode("Old San Juan, PR") is not None
    # Different casing/spacing hits the SAME cache entry (no second backend call).
    assert cb.geocode("old san juan,  pr") is not None
    assert backend.calls == 1


# ---------------------------------------------------------------- negative cache

def test_offline_all_miss_writes_no_marker(tmp_path: Path, monkeypatch):
    """THE load-bearing branch: offline all-miss must NOT persist a negative
    marker (it is permanent and would poison the address forever)."""
    monkeypatch.setenv("SPIDERWEB_OFFLINE", "1")
    backend = CountingFixtureBackend({})  # knows nothing → always None
    cb = CachedBackend([backend], cache_dir=tmp_path)

    assert cb.geocode("Calle Desconocida, Ponce") is None
    cache_file = tmp_path / f"{_addr_key('Calle Desconocida, Ponce')}.json"
    assert not cache_file.exists(), "offline all-miss must not write a negative marker"


def test_online_all_miss_writes_negative_marker_and_suppresses(tmp_path: Path):
    """Online all-miss writes a negative marker; the next call returns None
    WITHOUT re-invoking the backend."""
    backend = CountingFixtureBackend({})  # always None
    cb = CachedBackend([backend], cache_dir=tmp_path)

    assert cb.geocode("Calle Inexistente, Caguas") is None
    assert backend.calls == 1
    cache_file = tmp_path / f"{_addr_key('Calle Inexistente, Caguas')}.json"
    assert cache_file.exists()
    assert json.loads(cache_file.read_text())["negative"] is True

    # Second call: served from negative cache, backend not called again.
    assert cb.geocode("Calle Inexistente, Caguas") is None
    assert backend.calls == 1, "negative cache should suppress the backend"


def test_backend_fallthrough_order(tmp_path: Path):
    """First backend that returns a hit wins; earlier misses fall through."""
    miss = CountingFixtureBackend({})
    hit = CountingFixtureBackend({"San Juan": SJU})
    cb = CachedBackend([miss, hit], cache_dir=tmp_path)
    r = cb.geocode("San Juan")
    assert r is not None and r.lat == 18.4222
    assert miss.calls == 1 and hit.calls == 1


# ---------------------------------------------------------------- municipio PIP

def test_municipio_from_point_resolves_known_point():
    # San Juan interior point (INTPTLAT/INTPTLON from municipios.geojson).
    assert municipio_from_point(18.4222, -66.0691) == "San Juan"
    # Ponce interior point.
    assert municipio_from_point(18.0017, -66.6067) == "Ponce"


def test_municipio_from_point_out_of_pr_is_empty():
    # Miami — outside the PR bbox entirely.
    assert municipio_from_point(25.7617, -80.1918) == ""


def test_municipio_from_point_in_bbox_but_ocean_is_empty():
    # A point inside the PR bounding box but in the ocean (south of the island)
    # falls in no municipio polygon.
    assert municipio_from_point(17.7, -66.5) == ""
