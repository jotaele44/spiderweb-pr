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
    GeocodeBackendError,
    GeocodeResult,
    _addr_key,
    _norm_address,
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


# ------------------------------------------------ transient errors vs no-match

class _ErroringBackend:
    """Simulates a transport failure (timeout/429/5xx) on every call."""

    name = "erroring"

    def __init__(self):
        self.calls = 0

    def geocode(self, address):
        self.calls += 1
        raise GeocodeBackendError("simulated timeout")


def test_transient_error_writes_no_negative_marker(tmp_path: Path):
    """A transient transport error must NOT persist a (permanent) negative
    marker — otherwise one flaky request poisons the address forever."""
    err = _ErroringBackend()
    cb = CachedBackend([err], cache_dir=tmp_path)

    assert cb.geocode("Calle Flaky, Ponce") is None
    cache_file = tmp_path / f"{_addr_key('Calle Flaky, Ponce')}.json"
    assert not cache_file.exists(), "transient error must not write a negative marker"

    # Next call retries the backend (no negative marker is suppressing it).
    assert cb.geocode("Calle Flaky, Ponce") is None
    assert err.calls == 2


def test_error_then_hit_falls_through(tmp_path: Path):
    """An erroring backend doesn't abort the chain; a later backend can hit."""
    err = _ErroringBackend()
    hit = CountingFixtureBackend({"San Juan": SJU})
    cb = CachedBackend([err, hit], cache_dir=tmp_path)
    r = cb.geocode("San Juan")
    assert r is not None and r.lat == 18.4222
    assert err.calls == 1 and hit.calls == 1


# ------------------------------------------------ out-of-PR result rejection

MIAMI = GeocodeResult(25.7617, -80.1918, "fixture", "exact", "Miami, FL")


def test_out_of_pr_result_is_rejected(tmp_path: Path):
    """A provider returning a non-PR coordinate (ambiguous mainland street name)
    is rejected — never served or cached as a positive."""
    backend = CountingFixtureBackend({"Calle Ambigua": MIAMI})
    cb = CachedBackend([backend], cache_dir=tmp_path)
    assert cb.geocode("Calle Ambigua") is None
    cache_file = tmp_path / f"{_addr_key('Calle Ambigua')}.json"
    if cache_file.exists():
        # Acceptable to record a clean no-match, but never the bad coordinate.
        assert json.loads(cache_file.read_text()).get("negative") is True


# ------------------------------------------------ normalization / empty input

def test_norm_address_strips_accents_for_cache_dedup(tmp_path: Path):
    assert _norm_address("Bayamón, PR") == _norm_address("Bayamon, PR")
    backend = CountingFixtureBackend({"Bayamón, PR": SJU})
    cb = CachedBackend([backend], cache_dir=tmp_path)
    assert cb.geocode("Bayamón, PR") is not None
    assert cb.geocode("bayamon  pr") is not None   # accent/case/punct variant
    assert backend.calls == 1, "accent variants must share one cache entry"


def test_empty_address_short_circuits(tmp_path: Path):
    backend = CountingFixtureBackend({})
    cb = CachedBackend([backend], cache_dir=tmp_path)
    assert cb.geocode("") is None
    assert cb.geocode("   ") is None
    assert backend.calls == 0, "empty input must not reach the backend"


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


def _square_fc(name: str, lon: float, lat: float, d: float = 0.5) -> dict:
    """A 1-feature FeatureCollection: a square polygon centred on (lon, lat)."""
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"NAME": name},
            "geometry": {"type": "Polygon", "coordinates": [[
                [lon - d, lat - d], [lon + d, lat - d],
                [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d],
            ]]},
        }],
    }


def test_load_municipios_keyed_by_path(tmp_path: Path):
    """A second call with a DIFFERENT municipios_path must load THAT file, not
    silently reuse the first dataset (the old module-global cache bug)."""
    pt_lat, pt_lon = 18.4, -66.1  # inside the PR bbox
    p1 = tmp_path / "a.geojson"
    p2 = tmp_path / "b.geojson"
    p1.write_text(json.dumps(_square_fc("AlphaTown", pt_lon, pt_lat)))
    p2.write_text(json.dumps(_square_fc("BetaCity", pt_lon, pt_lat)))

    assert municipio_from_point(pt_lat, pt_lon, municipios_path=p1) == "AlphaTown"
    assert municipio_from_point(pt_lat, pt_lon, municipios_path=p2) == "BetaCity"
