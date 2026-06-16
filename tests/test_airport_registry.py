"""Guard: AASB AIRPORT_COORDS must stay in sync with the canonical registry.

`integration/aasb_airspace_bridge.AIRPORT_COORDS` is loaded from
`configs/airport_registry.yaml` (single source of truth). These tests pin that
contract so the runtime dict and the registry cannot silently diverge again.
"""

from pathlib import Path

from integration.aasb_airspace_bridge import (
    AIRPORT_COORDS,
    _LEGACY_IATA,
)
from pipeline.config_loader import load_yaml_config

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "configs" / "airport_registry.yaml"

EXPECTED_CODES = {"SJU", "BQN", "PSE", "SIG", "NRR", "MAZ", "ARE", "CPX", "VQS"}


def _registry():
    return load_yaml_config(REGISTRY, required_keys=["airports"])["airports"]


def test_airport_coords_has_exactly_expected_codes():
    assert set(AIRPORT_COORDS) == EXPECTED_CODES


def test_iata_codes_match_registry_coordinates():
    by_iata = {
        a["iata"]: (a["lat"], a["lon"])
        for a in _registry()
        if a.get("iata")
    }
    for code, coords in by_iata.items():
        assert code in AIRPORT_COORDS, f"{code} present in registry but not loaded"
        assert AIRPORT_COORDS[code] == coords, f"{code} coords diverge from registry"


def test_legacy_codes_resolve_to_their_icao_entry():
    by_icao = {a["icao"]: (a["lat"], a["lon"]) for a in _registry() if a.get("icao")}
    for legacy_code, icao in _LEGACY_IATA.items():
        assert icao in by_icao, f"legacy map points at unknown ICAO {icao}"
        assert AIRPORT_COORDS[legacy_code] == by_icao[icao]


def test_no_zero_sentinel_coordinates():
    # Every anchored airport must have real coordinates, never the (0,0) sentinel.
    for code, (lat, lon) in AIRPORT_COORDS.items():
        assert (lat, lon) != (0.0, 0.0), f"{code} has sentinel coordinates"
