#!/usr/bin/env python3
"""Materialize the reviewed v0.3 source bundle on its bounded feature branch."""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import zipfile

PAYLOAD_SHA256 = "b56be1796daf9901db04d5b16072876213716408e307e2636639d8fcf54a993d"
MEMBER_SHA256 = {
    "docs/ARCHIPELAGO_IDENTITY_GRAPH_V0_3.md": "d597f700b7851357cb8c6baf1bc2ac56299117adf7c88d540610176b4b53b0f9",
    "evidence/pr_archipelago/las_lavanderas_morphology_terminal_v0_3.json": "60d71fb0a7932fef8bbf6d3cf07befc8e09225fb69ec591a496d4be36d1ab94c",
    "evidence/pr_archipelago/sige_four_row_adjudication_v0_3.json": "8d2e23c0d89d61a778ba96b470e00c4b12f9b5b6f97e6523b1a1b4e839a30884",
    "scripts/materialize_pr_archipelago_identity_graph_v0_3.py": "8a28b049cddf043c401d60a384c3b1f0d73967fc6061e996cabd3aeaf20472a2",
    "spiderweb/spatial/archipelago_identity_graph_v0_3.py": "892db364989e83551a9b41dee8e0e23fcf7bd735921aa0775452a10e5b7d2d2f",
    "spiderweb/spatial/offshore_classifier_v0_3.py": "43ba053c043d769f7501b7c659c45ebefa31630807bcb54a49ff477877ccd6d2",
    "tests/test_archipelago_identity_graph_v0_3.py": "e9816bc2ae21e45566e9278b8f7def1395c8e6722996e448e39d42451ac265f3",
    "tests/test_offshore_classifier_v0_3.py": "b6ca0407f21a85d54d155bffdd203ad670747a48d661ae7f96c8370a202c50bc",
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    part_dir = root / ".federation/archipelago_identity_v0_3"
    parts = sorted(part_dir.glob("part_*.b64"))
    if [p.name for p in parts] != [f"part_{i:02d}.b64" for i in range(7)]:
        raise SystemExit("bootstrap part denominator mismatch")
    payload = base64.b64decode("".join(p.read_text(encoding="ascii") for p in parts))
    actual = hashlib.sha256(payload).hexdigest()
    if actual != PAYLOAD_SHA256:
        raise SystemExit(f"bootstrap payload hash mismatch: {actual} != {PAYLOAD_SHA256}")
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = sorted(name for name in zf.namelist() if not name.endswith("/"))
        if names != sorted(MEMBER_SHA256):
            raise SystemExit("bootstrap member denominator mismatch")
        for name in names:
            p = PurePosixPath(name)
            if p.is_absolute() or ".." in p.parts:
                raise SystemExit(f"unsafe member: {name}")
            data = zf.read(name)
            digest = hashlib.sha256(data).hexdigest()
            if digest != MEMBER_SHA256[name]:
                raise SystemExit(f"member hash mismatch: {name}")
            out = root / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
    print(json.dumps({"members": len(MEMBER_SHA256), "payload_sha256": actual, "state": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
