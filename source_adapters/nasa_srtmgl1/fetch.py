"""Download SRTMGL1 and SRTMGL1N granules from NASA LP DAAC (Earthdata Cloud).

Authentication is an Earthdata Login bearer token. Two ways to supply it:

* a network secret for ``data.lpdaac.earthdatacloud.nasa.gov`` that the egress
  proxy adds to each request (the code then sends no credential itself); or
* ``EARTHDATA_TOKEN`` in the environment, sent as ``Authorization: Bearer``.

LP DAAC answers an authenticated request with a redirect to a signed CloudFront
URL. ``Authorization`` is dropped whenever a redirect changes host, so the token
never reaches CloudFront. A redirect to the Earthdata Login OAuth page means the
request was not authenticated: it is refused, never followed. Signed URLs are
not recorded; provenance keeps the LP DAAC URL and the final host only.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, OpenerDirector, Request, build_opener

USER_AGENT = "spiderweb-pr-nasa-srtmgl1-adapter/1.0"
EDL_LOGIN_HOST = "urs.earthdata.nasa.gov"
TOKEN_ENV = "EARTHDATA_TOKEN"


class EarthdataLoginRequired(RuntimeError):
    """LP DAAC did not accept the request as authenticated."""


def _is_login_host(host: str) -> bool:
    return host == EDL_LOGIN_HOST or host.endswith("." + EDL_LOGIN_HOST)


def _drop_authorization(req: Request) -> None:
    for store in (req.headers, req.unredirected_hdrs):
        for key in [k for k in store if k.lower() == "authorization"]:
            del store[key]


class EarthdataRedirectHandler(HTTPRedirectHandler):
    """Follow LP DAAC's redirect to signed storage, never the login page."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        new_host = (urlsplit(newurl).hostname or "").lower()
        if _is_login_host(new_host):
            raise EarthdataLoginRequired(
                "Earthdata login required: LP DAAC redirected to the Earthdata Login page. "
                "Provide a bearer token (network secret for data.lpdaac.earthdatacloud.nasa.gov, "
                f"or {TOKEN_ENV})."
            )
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        old_host = (urlsplit(req.full_url).hostname or "").lower()
        if new is not None and new_host != old_host:
            _drop_authorization(new)
        return new


def default_opener() -> OpenerDirector:
    return build_opener(EarthdataRedirectHandler())


def token_from_env(env: Mapping[str, str] | None = None) -> str | None:
    value = (env if env is not None else os.environ).get(TOKEN_ENV, "").strip()
    return value or None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def download(
    url: str,
    dest: Path,
    *,
    opener: OpenerDirector | None = None,
    token: str | None = None,
    timeout: int = 180,
) -> dict[str, object]:
    """Stream ``url`` to ``dest`` and return its provenance row."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    accessed_at = utc_now()
    try:
        response = (opener or default_opener()).open(request, timeout=timeout)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise EarthdataLoginRequired(
                f"Earthdata login required: LP DAAC answered HTTP {exc.code} for {url}"
            ) from exc
        raise
    with response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise RuntimeError(f"unexpected HTTP status {status} for {url}")
        final_host = (urlsplit(response.geturl()).hostname or "").lower()
        if _is_login_host(final_host):
            raise EarthdataLoginRequired(f"Earthdata login required: ended at {final_host}")
        fd, tmp_name = tempfile.mkstemp(prefix=".partial-", dir=dest.parent)
        try:
            with os.fdopen(fd, "wb") as out:
                while True:
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            os.replace(tmp_name, dest)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
    return {
        "source_url": url,
        "final_host": final_host,
        "accessed_at": accessed_at,
        "file_name": dest.name,
        "file_size_bytes": size,
        "sha256": digest.hexdigest(),
        "raw_commit_allowed": False,
    }
