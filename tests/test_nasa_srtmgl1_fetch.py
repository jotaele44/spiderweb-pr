"""LP DAAC fetch: bearer token handling, redirect to signed storage, login refusal."""

from __future__ import annotations

import email.message
import hashlib
import io
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import BaseHandler, ProxyHandler, Request, build_opener
from urllib.response import addinfourl

import pytest

from source_adapters.nasa_srtmgl1 import cli
from source_adapters.nasa_srtmgl1.fetch import (
    EarthdataLoginRequired,
    EarthdataRedirectHandler,
    download,
    token_from_env,
)

LPDAAC = "https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/SRTMGL1N.003/N18W067.SRTMGL1N.num/N18W067.SRTMGL1N.num.zip"
SIGNED = "https://d1nklfio7vscoe.cloudfront.net/lp-prod-protected/N18W067.SRTMGL1N.num.zip?Signature=abc"
LOGIN = "https://urs.earthdata.nasa.gov/oauth/authorize?client_id=x"


def _headers(**values: str) -> email.message.Message:
    msg = email.message.Message()
    for k, v in values.items():
        msg[k.replace("_", "-")] = v
    return msg


class FakeHTTPS(BaseHandler):
    """Answers like LP DAAC: 303 to signed storage, then 200 with the payload.

    ``handler_order`` puts it ahead of urllib's real HTTPS handler, so no
    request leaves the process.
    """

    handler_order = 200

    def __init__(self, payload: bytes, first_hop: str = SIGNED) -> None:
        self.payload = payload
        self.first_hop = first_hop
        self.seen: list[tuple[str, str | None]] = []

    def https_open(self, req: Request):
        self.seen.append((req.full_url, req.get_header("Authorization")))
        if urlsplit(req.full_url).hostname == "data.lpdaac.earthdatacloud.nasa.gov":
            resp = addinfourl(io.BytesIO(b""), _headers(Location=self.first_hop), req.full_url, 303)
            resp.msg = "See Other"
            return resp
        resp = addinfourl(io.BytesIO(self.payload), _headers(Content_Type="application/zip"), req.full_url, 200)
        resp.msg = "OK"
        return resp


def _offline_opener(fake: FakeHTTPS):
    return build_opener(ProxyHandler({}), EarthdataRedirectHandler(), fake)


def test_redirect_to_other_host_drops_authorization() -> None:
    req = Request(LPDAAC, headers={"Authorization": "Bearer t0k"})
    new = EarthdataRedirectHandler().redirect_request(req, None, 303, "See Other", {}, SIGNED)
    assert new.get_header("Authorization") is None


def test_redirect_on_same_host_keeps_authorization() -> None:
    req = Request(LPDAAC, headers={"Authorization": "Bearer t0k"})
    new = EarthdataRedirectHandler().redirect_request(req, None, 307, "Temporary Redirect", {}, LPDAAC + "?again=1")
    assert new.get_header("Authorization") == "Bearer t0k"


def test_redirect_to_login_page_is_refused() -> None:
    req = Request(LPDAAC)
    with pytest.raises(EarthdataLoginRequired, match="Earthdata login required"):
        EarthdataRedirectHandler().redirect_request(req, None, 302, "Found", {}, LOGIN)


def test_full_redirect_chain_downloads_and_never_sends_token_to_storage(tmp_path: Path) -> None:
    payload = b"zip-bytes" * 1000
    fake = FakeHTTPS(payload)
    opener = _offline_opener(fake)
    row = download(LPDAAC, tmp_path / "N18W067.SRTMGL1N.num.zip", opener=opener, token="t0k")
    assert row["sha256"] == hashlib.sha256(payload).hexdigest()
    assert row["file_size_bytes"] == len(payload)
    assert row["final_host"] == "d1nklfio7vscoe.cloudfront.net"
    assert row["source_url"] == LPDAAC and "Signature" not in json.dumps(row)
    assert fake.seen == [(LPDAAC, "Bearer t0k"), (SIGNED, None)]
    assert (tmp_path / "N18W067.SRTMGL1N.num.zip").read_bytes() == payload


def test_chain_ending_at_login_page_leaves_no_file(tmp_path: Path) -> None:
    opener = _offline_opener(FakeHTTPS(b"", first_hop=LOGIN))
    with pytest.raises(EarthdataLoginRequired):
        download(LPDAAC, tmp_path / "x.zip", opener=opener)
    assert list(tmp_path.iterdir()) == []


def test_http_401_means_login_required(tmp_path: Path) -> None:
    class Refusing:
        def open(self, req, timeout=None):
            raise HTTPError(req.full_url, 401, "Unauthorized", _headers(), io.BytesIO(b""))

    with pytest.raises(EarthdataLoginRequired, match="HTTP 401"):
        download(LPDAAC, tmp_path / "x.zip", opener=Refusing())


def test_token_comes_from_env_only_when_set() -> None:
    assert token_from_env({}) is None
    assert token_from_env({"EARTHDATA_TOKEN": "  "}) is None
    assert token_from_env({"EARTHDATA_TOKEN": "abc"}) == "abc"


def test_cli_fetch_requires_acknowledgement(tmp_path: Path, capsys) -> None:
    assert cli.main(["fetch", "--tile", "N18W067", "--cache-dir", str(tmp_path)]) == 2
    assert "--acknowledge-no-commit" in capsys.readouterr().err


def test_cli_fetch_exits_3_when_login_required(tmp_path: Path, monkeypatch, capsys) -> None:
    def refuse(*args, **kwargs):
        raise EarthdataLoginRequired("Earthdata login required: test")

    monkeypatch.setattr(cli, "download", refuse)
    rc = cli.main(["fetch", "--tile", "N18W067", "--cache-dir", str(tmp_path), "--acknowledge-no-commit", "--num-only"])
    assert rc == 3
    assert "Earthdata login required" in capsys.readouterr().err


def test_cli_fetch_records_provenance(tmp_path: Path, monkeypatch) -> None:
    def fake_download(url, dest, **kwargs):
        dest.write_bytes(b"x")
        return {"source_url": url, "final_host": "cdn.example", "accessed_at": "2026-11-23T00:00:00Z",
                "file_name": dest.name, "file_size_bytes": 1, "sha256": hashlib.sha256(b"x").hexdigest(),
                "raw_commit_allowed": False}

    monkeypatch.setattr(cli, "download", fake_download)
    assert cli.main(["fetch", "--tile", "N18W067", "--cache-dir", str(tmp_path), "--acknowledge-no-commit"]) == 0
    prov = json.loads((tmp_path / "provenance.json").read_text())
    assert [(f["product"], f["tile_id"]) for f in prov["files"]] == [("SRTMGL1", "N18W067"), ("SRTMGL1N", "N18W067")]


def test_cli_discover_is_metadata_only(tmp_path: Path) -> None:
    pytest.importorskip("jsonschema")
    assert cli.main(["discover", "--out", str(tmp_path)]) == 0
    plan = json.loads((tmp_path / "fetch_plan.json").read_text())
    assert plan["metadata_only"] is True and len(plan["selected_tiles"]) == 6
    assert all(task["local_cache_path"] is None for task in plan["tasks"])
    assert plan["platform_policy"]["review_status"] == "pass"
