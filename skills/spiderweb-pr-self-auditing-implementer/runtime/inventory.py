from __future__ import annotations
from pathlib import Path
import hashlib

TEXT_SUFFIXES = {".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".csv"}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def inventory(root: Path) -> dict:
    files = []
    for p in sorted(x for x in root.rglob("*") if x.is_file() and ".git" not in x.parts):
        files.append({"path": str(p.relative_to(root)), "bytes": p.stat().st_size, "sha256": sha256(p), "text": p.suffix.lower() in TEXT_SUFFIXES})
    return {"root": str(root), "file_count": len(files), "files": files}
