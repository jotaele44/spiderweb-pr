from pathlib import Path
import zipfile

import pytest

from scripts.source_adapters.census_partnership_pr.fetch import (
    DownloadRecord,
    is_zip_payload,
    sha256_bytes,
    write_coverage_ledger,
)
from scripts.source_adapters.census_partnership_pr.normalize import extract_zip, extract_zip_tree, find_vector_inputs
from scripts.source_adapters.census_partnership_pr.parse_form import (
    make_batches,
    parse_partnership_form,
    select_municipios,
)


SAMPLE_HTML = """
<html>
  <body>
    <form method="post" action="/geo/partnerships/pvs/download">
      <input type="hidden" name="STATE" value="72" />
      <label><input type="checkbox" name="CNTY" value="72001" /> 72001 Adjuntas</label>
      <label><input type="checkbox" name="CNTY" value="72003" /> 72003 Aguada</label>
      <label><input type="checkbox" name="CNTY" value="72005" /> 72005 Aguadilla</label>
      <label><input type="checkbox" name="CNTY" value="72007" /> 72007 Aguas Buenas</label>
      <label><input type="checkbox" name="CNTY" value="72009" /> 72009 Aibonito</label>
      <label><input type="checkbox" name="CNTY" value="72011" /> 72011 Anasco</label>
    </form>
  </body>
</html>
"""


def test_parse_partnership_form_extracts_municipio_universe():
    form = parse_partnership_form(SAMPLE_HTML, "https://www.census.gov/root/st72_pr.html")

    assert form.method == "post"
    assert form.action_url == "https://www.census.gov/geo/partnerships/pvs/download"
    assert form.hidden_fields == (("STATE", "72"),)
    assert len(form.municipios) == 6
    assert form.municipios[0].code == "72001"
    assert form.municipios[0].name == "Adjuntas"


def test_batch_limit_is_enforced():
    batches = make_batches(["72001", "72003", "72005", "72007", "72009", "72011"])

    assert batches == [("72001", "72003", "72005", "72007", "72009"), ("72011",)]
    with pytest.raises(ValueError):
        make_batches(["72001"], batch_size=6)


def test_select_municipios_rejects_unknown_codes():
    form = parse_partnership_form(SAMPLE_HTML, "https://www.census.gov/root/st72_pr.html")

    selected = select_municipios(form, ["72003", "72001"])
    assert [municipio.code for municipio in selected] == ["72003", "72001"]
    with pytest.raises(ValueError):
        select_municipios(form, ["72099"])


def test_payload_validation_rejects_html_and_accepts_zip():
    assert is_zip_payload(b"PK\x03\x04abc", "application/zip")
    assert not is_zip_payload(b"<!doctype html><html>Error</html>", "text/html")
    assert not is_zip_payload(b"<html>Error</html>", "application/zip")


def test_sha256_bytes_is_stable():
    assert sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_coverage_ledger_reports_unresolved(tmp_path: Path):
    records = [
        DownloadRecord("b1", "72001", "u", "a", "POST", "[]", "t", 200, "application/zip", "x.zip", "abc", 10, "not_extracted", "", "raw", ""),
        DownloadRecord("b2", "72003", "u", "a", "POST", "[]", "t", 200, "text/html", "x.html", "def", 20, "not_extracted", "", "hold", "response_not_zip"),
    ]
    path = tmp_path / "coverage_ledger.csv"

    write_coverage_ledger(path, expected=78, selected=2, records=records)
    text = path.read_text(encoding="utf-8")

    assert "expected_municipios,selected_municipios,batch_count" in text
    assert "78,2,2,1,0,1,0,1,50.0" in text


def test_extract_zip_and_find_shapefiles(tmp_path: Path):
    zip_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("sample/sample.shp", b"placeholder")
        archive.writestr("sample/sample.dbf", b"placeholder")

    extracted = extract_zip(zip_path, tmp_path / "extracted")
    shapefiles = find_vector_inputs(extracted)

    assert [path.name for path in shapefiles] == ["sample.shp"]


def test_extract_zip_tree_recurses_into_nested_municipio_zips(tmp_path: Path):
    nested_zip = tmp_path / "72001.zip"
    with zipfile.ZipFile(nested_zip, "w") as archive:
        archive.writestr("72001/edges.shp", b"placeholder")
        archive.writestr("72001/edges.dbf", b"placeholder")

    outer_zip = tmp_path / "batch.zip"
    with zipfile.ZipFile(outer_zip, "w") as archive:
        archive.write(nested_zip, arcname="downloads/72001.zip")

    extracted = extract_zip_tree(outer_zip, tmp_path / "extracted")
    shapefiles = find_vector_inputs(extracted)

    assert [path.name for path in shapefiles] == ["edges.shp"]
