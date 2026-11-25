"""Read SRTMGL1 height (.hgt) and SRTMGL1N source-number (.num) files from their ZIPs.

Formats (SRTM User Guide V3): 3601 x 3601 samples, row-major from the north.
Heights are big-endian signed 16-bit metres on WGS84/EGM96; -32768 marks a void.
NUM files hold one unsigned byte per sample. A file of any other length is
refused rather than reshaped.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np

from .tiles import SAMPLES

HGT_BYTES = SAMPLES * SAMPLES * 2  # 25,934,402
NUM_BYTES = SAMPLES * SAMPLES  # 12,967,201
VOID = -32768


def _single_member(path: Path, suffix: str) -> bytes:
    with zipfile.ZipFile(path) as archive:
        members = [n for n in archive.namelist() if n.lower().endswith(suffix)]
        if len(members) != 1:
            raise ValueError(f"{path.name}: expected exactly one *{suffix} member, found {members}")
        return archive.read(members[0])


def read_hgt_zip(path: Path | str) -> np.ndarray:
    raw = _single_member(Path(path), ".hgt")
    if len(raw) != HGT_BYTES:
        raise ValueError(f"{Path(path).name}: .hgt is {len(raw)} bytes, expected {HGT_BYTES}")
    return np.frombuffer(raw, dtype=">i2").reshape(SAMPLES, SAMPLES).astype(np.int16)


def read_num_zip(path: Path | str) -> np.ndarray:
    raw = _single_member(Path(path), ".num")
    if len(raw) != NUM_BYTES:
        raise ValueError(f"{Path(path).name}: .num is {len(raw)} bytes, expected {NUM_BYTES}")
    return np.frombuffer(raw, dtype=np.uint8).reshape(SAMPLES, SAMPLES)


def height_stats(heights: np.ndarray) -> dict[str, object]:
    valid = heights[heights != VOID]
    return {
        "samples": int(heights.size),
        "void_samples": int(heights.size - valid.size),
        "min_m": int(valid.min()) if valid.size else None,
        "max_m": int(valid.max()) if valid.size else None,
    }
