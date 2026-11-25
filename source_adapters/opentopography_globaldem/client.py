"""Fetch clipped global DEMs from OpenTopography's ``/API/globaldem``.

OpenTopography's OpenAPI document declares ``API_Key`` as a required *query*
parameter with no header scheme, so the key travels in the URL. It is read from
``OPENTOPOGRAPHY_API_KEY`` (or ``OpenTopography_API_KEY``, the name Skywatcher's
GEBCO fetcher also reads) and is redacted from every URL this module returns,
logs or records. Errors are re-raised without the original exception, whose
attributes carry the full URL.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import OpenerDirector, Request, build_opener

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "data_sources" / "opentopography" / "globaldem.yml"
USER_AGENT = "spiderweb-pr-opentopography-globaldem/1.0"
REDACTED = "REDACTED"
_TIFF_MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")


class OpenTopographyKeyMissing(RuntimeError):
    pass


class OpenTopographyAuthError(RuntimeError):
    pass


class OpenTopographyRequestError(RuntimeError):
    pass


def load_config(path: Path | str = CONFIG_PATH) -> dict:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("source_family") != "OPENTOPOGRAPHY_GLOBALDEM":
        raise ValueError("not an OpenTopography globaldem config")
    return config


def demtypes(config: Mapping) -> dict[str, dict]:
    return {d["demtype"]: d for d in config["demtypes"]}


def api_key(config: Mapping, env: Mapping[str, str] | None = None) -> str | None:
    env = os.environ if env is None else env
    for name in config["api"]["key_env"]:
        value = env.get(name, "").strip()
        if value:
            return value
    return None


def build_request_url(
    config: Mapping, demtype: str, bbox_wsen: Sequence[float], key: str, output_format: str = "GTiff"
) -> str:
    if demtype not in demtypes(config):
        raise ValueError(f"demtype {demtype!r} is not registered in {CONFIG_PATH.name}")
    if output_format not in config["api"]["output_formats"]:
        raise ValueError(f"unsupported outputFormat {output_format!r}")
    west, south, east, north = bbox_wsen
    if not (west < east and south < north):
        raise ValueError("bbox must be (west, south, east, north) with west < east and south < north")
    query = {
        "demtype": demtype,
        "south": south,
        "north": north,
        "west": west,
        "east": east,
        "outputFormat": output_format,
        config["api"]["key_parameter"]: key,
    }
    return f"{config['api']['endpoint']}?{urlencode(query)}"


def redact(url: str, key_parameter: str = "API_Key") -> str:
    parts = urlsplit(url)
    query = [(k, REDACTED if k.lower() == key_parameter.lower() else v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit(parts._replace(query=urlencode(query, safe=REDACTED)))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch(
    config: Mapping,
    demtype: str,
    bbox_wsen: Sequence[float],
    dest: Path,
    *,
    key: str | None,
    opener: OpenerDirector | None = None,
    timeout: int = 300,
) -> dict[str, object]:
    if not key:
        names = " or ".join(config["api"]["key_env"])
        raise OpenTopographyKeyMissing(f"OpenTopography API key not set: export {names}")
    url = build_request_url(config, demtype, bbox_wsen, key)
    safe_url = redact(url, config["api"]["key_parameter"])
    request = Request(url, headers={"User-Agent": USER_AGENT})
    accessed_at = _utc_now()
    try:
        response = (opener or build_opener()).open(request, timeout=timeout)
    except HTTPError as exc:
        code = exc.code
        if code in (401, 403):
            raise OpenTopographyAuthError(f"OpenTopography refused the key (HTTP {code}) for {safe_url}") from None
        raise OpenTopographyRequestError(f"OpenTopography HTTP {code} for {safe_url}") from None
    except URLError as exc:
        raise OpenTopographyRequestError(f"OpenTopography request failed ({exc.reason}) for {safe_url}") from None

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    head = b""
    with response:
        content_type = response.headers.get("Content-Type", "")
        fd, tmp_name = tempfile.mkstemp(prefix=".partial-", dir=dest.parent)
        try:
            with os.fdopen(fd, "wb") as out:
                while True:
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    if len(head) < 4:
                        head += chunk[: 4 - len(head)]
                    out.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            if head not in _TIFF_MAGIC:
                raise OpenTopographyRequestError(
                    f"OpenTopography did not return a GeoTIFF (Content-Type {content_type!r}) for {safe_url}"
                )
            os.replace(tmp_name, dest)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
    entry = demtypes(config)[demtype]
    return {
        "demtype": demtype,
        "catalog_source_id": entry["catalog_source_id"],
        "opentopography_id": entry["opentopography_id"],
        "request_url": safe_url,
        "bbox_wsen": list(bbox_wsen),
        "accessed_at": accessed_at,
        "content_type": content_type,
        "file_name": dest.name,
        "file_size_bytes": size,
        "sha256": digest.hexdigest(),
        "raw_commit_allowed": False,
    }
