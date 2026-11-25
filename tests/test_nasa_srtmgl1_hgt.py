"""SRTM .hgt and .num readers refuse anything but the exact published layout."""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pytest

from source_adapters.nasa_srtmgl1.hgt import HGT_BYTES, NUM_BYTES, VOID, height_stats, read_hgt_zip, read_num_zip

N = 3601


def _zip(path: Path, member: str, payload: bytes) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, payload)
    return path


def test_sizes_match_the_user_guide() -> None:
    assert HGT_BYTES == 25_934_402
    assert NUM_BYTES == 12_967_201


def test_hgt_is_big_endian_row_major_from_the_north(tmp_path: Path) -> None:
    grid = np.zeros((N, N), dtype=">i2")
    grid[0, 0] = 1338  # north-west corner
    grid[N - 1, N - 1] = -21  # south-east corner
    grid[10, 20] = VOID
    path = _zip(tmp_path / "N18W067.SRTMGL1.hgt.zip", "N18W067.hgt", grid.tobytes())
    heights = read_hgt_zip(path)
    assert heights.shape == (N, N)
    assert heights[0, 0] == 1338 and heights[N - 1, N - 1] == -21
    stats = height_stats(heights)
    assert stats == {"samples": N * N, "void_samples": 1, "min_m": -21, "max_m": 1338}


def test_little_endian_bytes_would_read_differently(tmp_path: Path) -> None:
    grid = np.zeros((N, N), dtype="<i2")
    grid[0, 0] = 256
    heights = read_hgt_zip(_zip(tmp_path / "le.zip", "X.hgt", grid.tobytes()))
    assert heights[0, 0] == 1  # read as big-endian, as published


def test_wrong_size_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="expected 25934402"):
        read_hgt_zip(_zip(tmp_path / "short.zip", "X.hgt", b"\x00" * 1201 * 1201 * 2))
    with pytest.raises(ValueError, match="expected 12967201"):
        read_num_zip(_zip(tmp_path / "short_num.zip", "X.num", b"\x00" * 10))


def test_zip_must_hold_exactly_one_member(tmp_path: Path) -> None:
    path = tmp_path / "two.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("a.hgt", b"")
        archive.writestr("b.hgt", b"")
    with pytest.raises(ValueError, match="exactly one"):
        read_hgt_zip(path)


def test_num_reads_unsigned_bytes(tmp_path: Path) -> None:
    grid = np.full((N, N), 202, dtype=np.uint8)
    grid[5, 5] = 51
    num = read_num_zip(_zip(tmp_path / "N18W067.SRTMGL1N.num.zip", "N18W067.num", grid.tobytes()))
    assert num.dtype == np.uint8 and num[5, 5] == 51 and num[0, 0] == 202
