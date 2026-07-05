"""ASGI entrypoint with migrated-frontend compatibility endpoints installed.

Run with:
    python3 -m uvicorn server.backend.compat_app:app --reload --port 8000
"""
from __future__ import annotations

from .main import _rows, _stream_rag, app
from .compat_shim import install_compat_shim

install_compat_shim(app, _rows, _stream_rag)
