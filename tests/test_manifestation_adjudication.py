import io
import zipfile

from federation.manifestation_adjudication import *


def make_zip(path, rows, compression):
    with zipfile.ZipFile(path, "w", compression=compression) as z:
        for name, payload in rows:
            z.writestr(name, payload)


def test_byte_identical_and_distinct_regular_files(tmp_path):
    a=tmp_path/"a.nc"; b=tmp_path/"b.nc"; a.write_bytes(b"grid"); b.write_bytes(b"grid")
    assert compare_manifestations(a,b).classification == BYTE_IDENTICAL
    b.write_bytes(b"other")
    assert compare_manifestations(a,b).classification == DISTINCT_PAYLOADS


def test_archive_recompression_and_path_semantics(tmp_path):
    a=tmp_path/"a.zip"; b=tmp_path/"b.zip"; c=tmp_path/"c.zip"
    make_zip(a, [("tile/a.bin",b"123")], zipfile.ZIP_STORED)
    make_zip(b, [("tile/a.bin",b"123")], zipfile.ZIP_DEFLATED)
    make_zip(c, [("renamed/a.bin",b"123")], zipfile.ZIP_DEFLATED)
    assert compare_manifestations(a,b).classification == PURE_RECOMPRESSION
    assert compare_manifestations(a,c).classification == SAME_PAYLOADS_DIFFERENT_PATHS


def test_missing_is_unresolved(tmp_path):
    assert compare_manifestations(tmp_path/"missing", tmp_path/"also-missing").classification == UNRESOLVED
