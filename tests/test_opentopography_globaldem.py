"""OpenTopography adapter: request parameters and the API key never leaving memory."""

from __future__ import annotations

import email.message
import io
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from source_adapters.opentopography_globaldem import cli
from source_adapters.opentopography_globaldem.client import (
    OpenTopographyAuthError,
    OpenTopographyKeyMissing,
    OpenTopographyRequestError,
    api_key,
    build_request_url,
    fetch,
    load_config,
    redact,
)

KEY = "k3y-that-must-not-leak"
BOX = (-66.62, 18.15, -66.56, 18.20)
TIFF = b"II*\x00" + b"\x00" * 64


class FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes, content_type: str = "image/tiff") -> None:
        super().__init__(payload)
        self.headers = email.message.Message()
        self.headers["Content-Type"] = content_type
        self.status = 200


class FakeOpener:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response, self.error, self.urls = response, error, []

    def open(self, req, timeout=None):
        self.urls.append(req.full_url)
        if self.error:
            raise self.error
        return self.response


@pytest.fixture(scope="module")
def config() -> dict:
    return load_config()


def test_request_url_carries_documented_parameters(config: dict) -> None:
    url = build_request_url(config, "COP30", BOX, KEY)
    query = parse_qs(urlsplit(url).query)
    assert urlsplit(url).path == "/API/globaldem"
    assert query["demtype"] == ["COP30"] and query["outputFormat"] == ["GTiff"]
    assert (query["west"], query["south"], query["east"], query["north"]) == (["-66.62"], ["18.15"], ["-66.56"], ["18.2"])
    assert query["API_Key"] == [KEY]


def test_redact_removes_the_key(config: dict) -> None:
    safe = redact(build_request_url(config, "SRTMGL1", BOX, KEY))
    assert KEY not in safe and "API_Key=REDACTED" in safe


def test_unknown_demtype_and_bad_box_are_refused(config: dict) -> None:
    with pytest.raises(ValueError):
        build_request_url(config, "GEDI_L3", BOX, KEY)
    with pytest.raises(ValueError):
        build_request_url(config, "COP30", (BOX[2], BOX[1], BOX[0], BOX[3]), KEY)


def test_key_is_read_from_either_variable(config: dict) -> None:
    assert api_key(config, {}) is None
    assert api_key(config, {"OPENTOPOGRAPHY_API_KEY": KEY}) == KEY
    assert api_key(config, {"OpenTopography_API_KEY": KEY}) == KEY


def test_missing_key_is_refused(config: dict, tmp_path: Path) -> None:
    with pytest.raises(OpenTopographyKeyMissing):
        fetch(config, "COP30", BOX, tmp_path / "x.tif", key=None)


def test_successful_fetch_records_no_key(config: dict, tmp_path: Path) -> None:
    opener = FakeOpener(FakeResponse(TIFF))
    row = fetch(config, "COP30", BOX, tmp_path / "cop30.tif", key=KEY, opener=opener)
    assert KEY in opener.urls[0]  # sent to OpenTopography...
    assert KEY not in json.dumps(row)  # ...and recorded nowhere
    assert row["catalog_source_id"] == "copernicus_glo30_dem"
    assert row["file_size_bytes"] == len(TIFF) and (tmp_path / "cop30.tif").exists()


def test_refused_key_error_hides_the_url(config: dict, tmp_path: Path) -> None:
    url = build_request_url(config, "COP30", BOX, KEY)
    opener = FakeOpener(error=HTTPError(url, 401, "Unauthorized", email.message.Message(), io.BytesIO(b"")))
    with pytest.raises(OpenTopographyAuthError) as excinfo:
        fetch(config, "COP30", BOX, tmp_path / "x.tif", key=KEY, opener=opener)
    assert KEY not in str(excinfo.value)
    assert excinfo.value.__cause__ is None and excinfo.value.__suppress_context__


def test_non_tiff_answer_leaves_no_file(config: dict, tmp_path: Path) -> None:
    opener = FakeOpener(FakeResponse(b"<error>API Key required</error>", "application/xml"))
    with pytest.raises(OpenTopographyRequestError, match="did not return a GeoTIFF"):
        fetch(config, "COP30", BOX, tmp_path / "x.tif", key=KEY, opener=opener)
    assert list(tmp_path.iterdir()) == []


def test_cli_plan_never_prints_the_key(monkeypatch, capsys) -> None:
    monkeypatch.setenv("OPENTOPOGRAPHY_API_KEY", KEY)
    assert cli.main(["plan"]) == 0
    out = capsys.readouterr().out
    assert KEY not in out
    plan = json.loads(out)
    assert plan["key_present"] is True and len(plan["requests"]) == 4


def test_cli_fetch_exit_codes(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.delenv("OPENTOPOGRAPHY_API_KEY", raising=False)
    monkeypatch.delenv("OpenTopography_API_KEY", raising=False)
    assert cli.main(["fetch", "--demtype", "COP30", "--cache-dir", str(tmp_path)]) == 2
    assert cli.main(["fetch", "--demtype", "COP30", "--cache-dir", str(tmp_path), "--acknowledge-no-commit"]) == 2
    assert "OPENTOPOGRAPHY_API_KEY" in capsys.readouterr().err
