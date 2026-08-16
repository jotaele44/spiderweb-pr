from __future__ import annotations

import json
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import uvicorn
import yaml
from fastapi import FastAPI

from server.backend.martin_ingress import create_router

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "configs" / "martin_delivery.yaml"


class UpstreamHandler(BaseHTTPRequestHandler):
    etag = '"martin-ingress-fixture"'

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        if not self.path.startswith("/municipios"):
            self.send_response(404)
            self.end_headers()
            return
        if self.headers.get("If-None-Match") == self.etag:
            self.send_response(304)
            self.send_header("ETag", self.etag)
            self.send_header("Cache-Control", "public, max-age=60")
            self.end_headers()
            return
        payload = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("ETag", self.etag)
        self.send_header("Cache-Control", "public, max-age=60")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _get(url: str, headers: dict[str, str] | None = None) -> tuple[int, bytes, dict[str, str]]:
    req = Request(url, headers=headers or {}, method="GET")
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, response.read(), {k.lower(): v for k, v in response.headers.items()}
    except HTTPError as exc:
        return exc.code, exc.read(), {k.lower(): v for k, v in exc.headers.items()}


def main() -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    assert registry["sources"]["municipios"]["publication_state"] == "validated"

    with tempfile.TemporaryDirectory() as td:
        temp_registry = Path(td) / "registry.yaml"
        test_registry = json.loads(json.dumps(registry))
        test_registry["sources"]["municipios"]["publication_state"] = "published"
        temp_registry.write_text(yaml.safe_dump(test_registry, sort_keys=False), encoding="utf-8")

        upstream = ThreadingHTTPServer(("127.0.0.1", 3000), UpstreamHandler)
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()

        app = FastAPI()
        app.include_router(create_router(registry_path=temp_registry))
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18001, log_level="error"))
        api_thread = threading.Thread(target=server.run, daemon=True)
        api_thread.start()
        for _ in range(50):
            if server.started:
                break
            time.sleep(0.1)
        assert server.started, "ingress test server did not start"

        status, payload, headers = _get("http://127.0.0.1:18001/tiles/municipios")
        assert status == 200, status
        assert payload == b'{"ok":true}'
        assert headers.get("etag") == UpstreamHandler.etag
        assert headers.get("cache-control") == "public, max-age=60"
        assert headers.get("content-type", "").startswith("application/json")

        status, _, headers304 = _get(
            "http://127.0.0.1:18001/tiles/municipios",
            {"If-None-Match": UpstreamHandler.etag},
        )
        assert status == 304, status
        assert headers304.get("etag") == UpstreamHandler.etag

        status, _, _ = _get("http://127.0.0.1:18001/tiles/not-authorized")
        assert status == 404, status
        status, _, _ = _get("http://127.0.0.1:18001/tiles/%2e%2e/secret")
        assert status in (404, 422), status

        upstream.shutdown()
        upstream.server_close()
        status, _, _ = _get("http://127.0.0.1:18001/tiles/municipios")
        assert status == 503, status

        server.should_exit = True
        api_thread.join(timeout=5)

    assert yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["sources"]["municipios"]["publication_state"] == "validated"
    print("PASS: production ingress preserves ETag/cache/304, fails visible, rejects unknown/path traversal, and does not mutate publication")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
