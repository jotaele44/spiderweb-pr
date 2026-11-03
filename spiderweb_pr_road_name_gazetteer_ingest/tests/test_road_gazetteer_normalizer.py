from pipeline.road_gazetteer_ingest import normalize_name, route_number_from_text, alias_variants

def test_normalize_pr_route():
    assert normalize_name('Puerto Rico Highway 191') == 'PR-191'
    assert normalize_name('PR 52') == 'PR-52'

def test_route_number_from_text():
    assert route_number_from_text('Carretera PR-191') == '191'
    assert route_number_from_text('Puerto Rico Highway 52') == '52'
    assert route_number_from_text('Avenida Winston Churchill') == ''

def test_alias_variants():
    vals = [x[0] for x in alias_variants('191', 'Carretera PR-191')]
    assert 'PR-191' in vals
    assert 'Puerto Rico Highway 191' in vals

from pipeline.road_gazetteer_ingest import (
    km_marker_from_text,
    parse_route_ref,
    road_class_network,
    route_number_band,
    split_route_number,
)


def test_route_number_band_edges():
    assert route_number_band('1') == 'primary_band'
    assert route_number_band('99') == 'primary_band'
    assert route_number_band('100') == 'secondary_band'
    assert route_number_band('299') == 'secondary_band'
    assert route_number_band('300') == 'tertiary_band'
    assert route_number_band('9999') == 'tertiary_band'
    assert route_number_band('0') == 'unknown'
    assert route_number_band('') == 'unknown'
    assert route_number_band(None) == 'unknown'


def test_split_route_number_suffix():
    assert split_route_number('3R') == ('3', 'R')
    assert split_route_number('191') == ('191', '')
    assert split_route_number('052') == ('52', '')
    assert split_route_number('') == ('', '')


def test_parse_route_ref_variants():
    assert parse_route_ref('Carretera 191')['route_number_band'] == 'secondary_band'
    assert parse_route_ref('Route PR-303')['route_number_band'] == 'tertiary_band'
    assert parse_route_ref('Puerto Rico Highway 52')['route_number_band'] == 'primary_band'
    r = parse_route_ref('Carr. 3R Km 12.4')
    assert r['route_number'] == '3R'
    assert r['base_number'] == '3'
    assert r['is_ramal'] is True
    assert r['km'] == 12.4
    assert parse_route_ref('Calle Luna')['route_number_band'] == 'unknown'


def test_km_marker_with_hectometre():
    assert km_marker_from_text('Carr. 3 Km 5 Hm 2') == 5.2
    assert km_marker_from_text('PR-2 km 10,5') == 10.5
    assert km_marker_from_text('PR-2') is None


def test_ramal_aliases():
    vals = [x[0] for x in alias_variants('3R', 'PR-3R')]
    assert 'Ramal 3' in vals
    assert 'PR-3 Ramal' in vals
    assert 'Ramal 191' not in [x[0] for x in alias_variants('191')]


def test_road_class_network():
    assert road_class_network('Primaria Urbana') == 'primary'
    assert road_class_network('Secundaria') == 'secondary'
    assert road_class_network('Terciaria') == 'tertiary'
    assert road_class_network('M') == ''
