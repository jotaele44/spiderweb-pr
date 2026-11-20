"""Offline adversarial postal-route tests; no USPS source claims."""
import pytest

from postal_routes import (
    Classification, RouteContext, binding_eligible, parse_designation,
    reconcile_candidates,
)

@pytest.mark.parametrize("raw,typ,route,box,normalized", [
    ("HC 1 BOX 5191", "HC", "1", "5191", "HC 1 BOX 5191"),
    ("hc 001 box 0003", "HC", "001", "0003", "HC 001 BOX 0003"),
    ("RR 2 BOX 40", "RR", "2", "40", "RR 2 BOX 40"),
    (" RR  4A  BOX 9B ", "RR", "4A", "9B", "RR 4A BOX 9B"),
    ("HC 1", "HC", "1", None, "HC 1"),
])
def test_supported_syntax_only(raw, typ, route, box, normalized):
    p = parse_designation(raw)
    assert (p.route_type, p.route_number, p.box_number, p.normalized_candidate) == (
        typ, route, box, normalized
    )
    assert p.classification == Classification.CANDIDATE

def test_ambiguous_map_label_fails_closed():
    p = parse_designation("Rural Route HC 1 5191")
    assert p.raw == "Rural Route HC 1 5191"
    assert p.normalized_candidate == "HC 1 BOX 5191"
    assert p.classification == Classification.AMBIGUOUS
    assert not binding_eligible(p, RouteContext(
        postal_system="USPS", authoritative_route_id="ID1", source_id="source1"
    ))

@pytest.mark.parametrize("raw", [
    "", "5191", "HC", "RR", "HC 1 5191", "RURAL ROUTE 1 BOX 4",
    "HC 1 BOX", "HC 1 BOX -1", "HC 1 BOX 4 EXTRA",
    "123 MAIN ST", "CONTRACT HCR 123", "HC 1 BOX 4;DROP TABLE",
])
def test_unsupported_does_not_promote(raw):
    assert parse_designation(raw).classification == Classification.UNRECOGNIZED

def test_string_type_and_zip_are_not_identity():
    p = parse_designation("HC 1 BOX 5191")
    assert not binding_eligible(p, RouteContext(postal_system="USPS", servicing_zip="00900"))
    assert not binding_eligible(p, RouteContext(
        postal_system="USPS", authoritative_route_id="R1"
    ))
    assert not binding_eligible(p, RouteContext(
        postal_system="OTHER", authoritative_route_id="R1", source_id="src"
    ))

def test_authoritative_id_still_requires_review():
    a = parse_designation("HC 1 BOX 3")
    b = parse_designation("HC 1 BOX 4")
    x = RouteContext(postal_system="USPS", authoritative_route_id="R1", source_id="s1")
    y = RouteContext(postal_system="USPS", authoritative_route_id="R1", source_id="s2")
    assert binding_eligible(a, x)
    assert reconcile_candidates(a, x, b, y) == "REVIEW"

def test_conflicting_authoritative_ids_are_not_merged():
    a = parse_designation("HC 1 BOX 3")
    x = RouteContext(postal_system="USPS", authoritative_route_id="R1", source_id="s1")
    y = RouteContext(postal_system="USPS", authoritative_route_id="R2", source_id="s2")
    assert reconcile_candidates(a, x, a, y) == "CONTRADICTION"

def test_different_route_strings_conflict_even_with_same_id():
    a = parse_designation("HC 1 BOX 3")
    b = parse_designation("HC 2 BOX 3")
    x = RouteContext(postal_system="USPS", authoritative_route_id="R1", source_id="s1")
    assert reconcile_candidates(a, x, b, x) == "CONTRADICTION"

def test_non_string_and_oversize_rejected():
    with pytest.raises(TypeError):
        parse_designation(None)
    with pytest.raises(ValueError):
        parse_designation("x" * 513)
