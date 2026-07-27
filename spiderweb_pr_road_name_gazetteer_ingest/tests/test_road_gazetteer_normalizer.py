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
