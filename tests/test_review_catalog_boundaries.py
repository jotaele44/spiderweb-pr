import pytest

from server.backend import main


@pytest.mark.parametrize(
    "document",
    [
        "[]",
        "scalar",
        "families: null",
        "families: [null]",
        "families: [{layers: null}]",
        "families: [{layers: [{}]}]",
        "families: [{layers: [{layer_id: []}]}]",
    ],
)
def test_malformed_catalog_uses_fallback(tmp_path, monkeypatch, document):
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(document)
    monkeypatch.setattr(main, "CATALOG_PATH", catalog)
    assert main._load_layer_catalog() == {}


def test_valid_catalog_preserved(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("families: [{layers: [{layer_id: municipios}]}]")
    monkeypatch.setattr(main, "CATALOG_PATH", catalog)
    assert (
        main._load_layer_catalog()["families"][0]["layers"][0]["layer_id"]
        == "municipios"
    )
