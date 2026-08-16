from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml
from fastapi import APIRouter, HTTPException, Request as FastAPIRequest, Response

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "configs" / "martin_delivery.yaml"
UPSTREAM_BASE_URL = "http://127.0.0.1:3000"
PASSTHROUGH_HEADERS = {"content-type", "etag", "cache-control", "last-modified", "expires"}


def published_source_ids(registry_path: Path = REGISTRY_PATH) -> set[str]:
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    sources = registry.get("sources", {})
    return {
        source["martin_source_id"]
        for source in sources.values()
        if source.get("publication_state") == "published"
        and source.get("visibility_required") == "V3"
    }


def _fetch(url: str, if_none_match: str | None) -> tuple[int, bytes, dict[str, str]]:
    headers = {}
    if if_none_match:
        headers["If-None-Match"] = if_none_match
    req = Request(url, method="GET", headers=headers)
    try:
        with urlopen(req, timeout=5) as resp:
            payload = resp.read()
            out_headers = {
                key.lower(): value
                for key, value in resp.headers.items()
                if key.lower() in PASSTHROUGH_HEADERS
            }
            return resp.status, payload, out_headers
    except HTTPError as exc:
        payload = exc.read()
        out_headers = {
            key.lower(): value
            for key, value in exc.headers.items()
            if key.lower() in PASSTHROUGH_HEADERS
        }
        return exc.code, payload, out_headers
    except URLError as exc:
        raise RuntimeError(str(exc)) from exc


def create_router(
    registry_path: Path = REGISTRY_PATH,
    upstream_base_url: str = UPSTREAM_BASE_URL,
) -> APIRouter:
    if upstream_base_url != UPSTREAM_BASE_URL:
        raise ValueError("Martin upstream is fixed; arbitrary proxy targets are forbidden")

    router = APIRouter(prefix="/tiles", tags=["martin-delivery"])

    def require_published(source_id: str) -> None:
        if source_id not in published_source_ids(registry_path):
            raise HTTPException(status_code=404, detail="Martin source is not published")

    async def proxy(path: str, request: FastAPIRequest) -> Response:
        try:
            status, payload, headers = await asyncio.to_thread(
                _fetch,
                f"{upstream_base_url}/{path}",
                request.headers.get("if-none-match"),
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="Martin upstream unavailable") from exc
        return Response(content=payload, status_code=status, headers=headers)

    @router.get("/{source_id}")
    async def tilejson(source_id: str, request: FastAPIRequest) -> Response:
        require_published(source_id)
        return await proxy(source_id, request)

    @router.get("/{source_id}/{z}/{x}/{y}")
    async def tile(source_id: str, z: int, x: int, y: int, request: FastAPIRequest) -> Response:
        require_published(source_id)
        if min(z, x, y) < 0:
            raise HTTPException(status_code=404, detail="invalid tile coordinate")
        return await proxy(f"{source_id}/{z}/{x}/{y}", request)

    return router


router = create_router()


def observability_snapshot(registry_path: Path = REGISTRY_PATH) -> dict[str, object]:
    published = sorted(published_source_ids(registry_path))
    return {
        "martin_upstream": UPSTREAM_BASE_URL,
        "authorized_published_source_count": len(published),
        "authorized_published_sources": published,
        "publication_gate": "published+V3",
        "arbitrary_proxy_target": False,
    }
