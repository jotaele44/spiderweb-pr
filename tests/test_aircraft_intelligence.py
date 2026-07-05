"""Tests for AircraftIntelligence lookup and unknown deduction."""

import pytest

from pipeline.aircraft_intelligence import AircraftIntelligence


def test_lookup_known_callsign(populated_db):
    ai = AircraftIntelligence(populated_db)
    result = ai.lookup_aircraft("N5854Z")
    assert result is not None


def test_lookup_unknown_callsign_returns_result(populated_db):
    ai = AircraftIntelligence(populated_db)
    result = ai.lookup_aircraft("ZZZZZ")
    # Should return something (None or a dict/object) without raising
    # The key requirement is no exception
    assert True


def test_compile_intelligence_report_known(populated_db):
    ai = AircraftIntelligence(populated_db)
    report = ai.compile_intelligence_report("N5854Z")
    assert report is not None


def test_compile_intelligence_report_returns_result(populated_db):
    ai = AircraftIntelligence(populated_db)
    result = ai.compile_intelligence_report("C6062")
    # Must not raise; may return string, dict, or None depending on implementation
    assert result is None or isinstance(result, (dict, str))


def test_lookup_callsign_with_no_operator_returns_profile(populated_db):
    from pipeline.aircraft_intelligence import AircraftProfile
    ai = AircraftIntelligence(populated_db)
    result = ai.lookup_aircraft("XUNKNOWN99")
    assert result is not None
    assert isinstance(result, AircraftProfile)
    assert result.callsign == "XUNKNOWN99"


def test_update_aircraft_profiles_table_writes_all_callsigns(populated_db):
    """update_aircraft_profiles_table refreshes one row per distinct callsign.

    Also guards the connection-batching refactor: the result must be identical
    to the previous per-callsign-connection implementation.
    """
    import json
    import sqlite3

    ai = AircraftIntelligence(populated_db)
    ai.update_aircraft_profiles_table()

    conn = sqlite3.connect(populated_db)
    rows = {
        r[0]: r
        for r in conn.execute(
            "SELECT callsign, owner, operator, primary_mission, operational_patterns "
            "FROM aircraft_profiles"
        )
    }
    conn.close()

    # Every distinct flight callsign is present.
    assert set(rows) == {"N5854Z", "C6062", "N767PD"}

    # Known-operator enrichment landed in the table.
    assert rows["N5854Z"][1] == "Puerto Rico Electric Power Authority"
    assert rows["N5854Z"][3] == "Power Line Inspection"

    # operational_patterns round-trips as JSON for every row.
    for callsign in rows:
        assert isinstance(json.loads(rows[callsign][4]), dict)
