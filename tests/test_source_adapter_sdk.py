import json
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from scripts.source_adapters.sdk import (
    AdapterPolicy,
    CoverageSummary,
    DownloadResult,
    PayloadRequest,
    PayloadValidator,
    SourceAdapterError,
    SourceEndpoint,
)
from scripts.source_adapters.sdk.core import normalize_param_pairs
from scripts.source_adapters.sdk.download import DownloadEngine
from scripts.source_adapters.sdk.form import parse_first_form
from scripts.source_adapters.sdk.manifest import ManifestEngine, summarize_coverage


class _FakeResponse:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return b'{"ok": true}'


def test_adapter_policy_rejects_raw_commit_permission(tmp_path: Path):
    policy = AdapterPolicy(
        raw_payload_root=tmp_path / "raw",
        manifest_root=tmp_path / "manifests",
        allow_raw_commit=True,
    )

    try:
        policy.validate_runtime_paths()
    except SourceAdapterError as exc:
        assert "must not allow" in str(exc)
    else:
        raise AssertionError("policy should reject raw commit permission")


def test_payload_validator_rejects_html_as_zip():
    assert PayloadValidator.is_zip(b"PK\x03\x04abc", "application/zip")
    assert not PayloadValidator.is_zip(b"<html>Error</html>", "application/zip")
    assert not PayloadValidator.matches_expected(b"<!doctype html><html></html>", "text/html", "zip")


def test_parse_first_form_collects_hidden_and_checkboxes():
    form = parse_first_form(
        """
        <form method="post" action="/download">
          <input type="hidden" name="state" value="72" />
          <label><input type="checkbox" name="county" value="72001" /> Adjuntas</label>
        </form>
        """,
        "https://example.gov/root/page.html",
    )

    assert form.method == "post"
    assert form.action_url == "https://example.gov/download"
    assert form.hidden_fields == (("state", "72"),)
    assert form.checkboxes[0].label == "Adjuntas"


def test_manifest_engine_writes_ledgers(tmp_path: Path):
    record = DownloadResult(
        request_id="r1",
        source_id="src",
        source_url="https://example.gov/file.zip",
        request_method="GET",
        request_params="{}",
        download_timestamp_utc="2026-01-01T00:00:00Z",
        http_status=200,
        content_type="application/zip",
        filename="file.zip",
        sha256="abc",
        bytes=10,
        review_status="raw",
    )
    engine = ManifestEngine(tmp_path)

    engine.write_download_ledger([record])
    engine.write_sha256_manifest([record])
    engine.write_coverage_ledger(summarize_coverage(expected=1, requested=1, records=[record]))

    assert (tmp_path / "download_ledger.csv").exists()
    assert (tmp_path / "sha256_manifest.csv").exists()
    coverage = (tmp_path / "coverage_ledger.csv").read_text(encoding="utf-8")
    assert "100.0" in coverage


def test_core_request_and_coverage_contracts():
    endpoint = SourceEndpoint(source_id="usgs_demo", name="USGS Demo", url="https://example.gov")
    request = PayloadRequest(request_id="r1", endpoint=endpoint, params={"q": "Puerto Rico"}, expected_content="json")
    summary = CoverageSummary(expected=3, requested=2, acquired=1, failed=1, hold=0, unresolved=1)

    assert request.endpoint.source_id == "usgs_demo"
    assert request.param_pairs() == (("q", "Puerto Rico"),)
    assert summary.coverage_pct == 50.0


def test_normalize_param_pairs_preserves_explicit_duplicate_keys():
    params = (("CNTY", "72001"), ("CNTY", "72003"), ("STATE", 72))

    assert normalize_param_pairs(params) == (
        ("CNTY", "72001"),
        ("CNTY", "72003"),
        ("STATE", "72"),
    )


def test_normalize_param_pairs_expands_mapping_list_values():
    params = {"CNTY": ["72001", "72003"], "STATE": "72"}

    assert normalize_param_pairs(params) == (
        ("CNTY", "72001"),
        ("CNTY", "72003"),
        ("STATE", "72"),
    )


def test_download_engine_get_preserves_duplicate_keys_and_manifest_parity(tmp_path: Path, monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr("scripts.source_adapters.sdk.download.urlopen", fake_urlopen)
    request = PayloadRequest(
        request_id="counties",
        endpoint=SourceEndpoint(
            source_id="census",
            name="Census",
            url="https://example.gov/download?mode=batch",
        ),
        params=(("CNTY", "72001"), ("CNTY", "72003"), ("STATE", "72")),
        expected_content="json",
    )

    result = DownloadEngine(tmp_path).download(request)

    query_pairs = parse_qsl(urlsplit(captured["request"].full_url).query, keep_blank_values=True)
    assert query_pairs == [
        ("mode", "batch"),
        ("CNTY", "72001"),
        ("CNTY", "72003"),
        ("STATE", "72"),
    ]
    assert json.loads(result.request_params) == [
        ["CNTY", "72001"],
        ["CNTY", "72003"],
        ["STATE", "72"],
    ]
    assert result.review_status == "raw"


def test_download_engine_post_expands_list_values_with_doseq(tmp_path: Path, monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return _FakeResponse()

    monkeypatch.setattr("scripts.source_adapters.sdk.download.urlopen", fake_urlopen)
    request = PayloadRequest(
        request_id="counties",
        endpoint=SourceEndpoint(
            source_id="census",
            name="Census",
            url="https://example.gov/download",
            method="POST",
        ),
        params={"CNTY": ["72001", "72003"], "STATE": 72},
        expected_content="json",
    )

    result = DownloadEngine(tmp_path).download(request)

    assert parse_qsl(captured["request"].data.decode("utf-8"), keep_blank_values=True) == [
        ("CNTY", "72001"),
        ("CNTY", "72003"),
        ("STATE", "72"),
    ]
    assert json.loads(result.request_params) == [
        ["CNTY", "72001"],
        ["CNTY", "72003"],
        ["STATE", "72"],
    ]
