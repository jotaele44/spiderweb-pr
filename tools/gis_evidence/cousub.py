"""Parse the preserved COUSUB DBF and compare a separately frozen table.

No network code: obtaining TIGERweb remains a separate action after a verified
COUSUB receipt. Expected subclass counts are hypotheses until actually counted.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path, PurePosixPath
import re
import struct
import zipfile
from .core import checked_bytes, digest, id_index, set_receipt, write_new

EXPECTED_SIZE = 3934254
EXPECTED_SHA256 = "6930acc0987823109e570a04507c48991a4e446802648054d3661b104aab989c"
EXPECTED_LSADC = {"20": 827, "41": 75, "00": 37}


def parse_dbf(data: bytes) -> tuple[list[dict], dict]:
    """Read native ASCII GEOID/LSADC fields; retain padded raw strings and bytes.

    The original archive remains unchanged. Other field bytes are not decoded
    under a guessed codepage. Deleted DBF records are reported and fail closed.
    """
    if len(data) < 33 or data[0] not in {3, 131}:
        raise ValueError("UNSUPPORTED_DBF_HEADER")
    count, header_len, record_len = struct.unpack_from("<IHH", data, 4)
    if header_len < 33 or (header_len - 33) % 32 or record_len < 2:
        raise ValueError("MALFORMED_DBF_LAYOUT")
    if header_len + count * record_len > len(data) or data[header_len-1] != 13:
        raise ValueError("TRUNCATED_DBF")
    fields = []; offset = 1
    for p in range(32, header_len-1, 32):
        name = data[p:p+11].split(b"\0", 1)[0].decode("ascii")
        typ = chr(data[p+11]); width = data[p+16]
        if not name or name in {x["name"] for x in fields} or width == 0:
            raise ValueError("INVALID_OR_DUPLICATE_DBF_FIELD")
        fields.append({"name":name,"type":typ,"width":width,"offset":offset})
        offset += width
    if offset != record_len:
        raise ValueError("DBF_RECORD_WIDTH_MISMATCH")
    wanted = {x["name"]:x for x in fields if x["name"] in {"GEOID","LSADC"}}
    if set(wanted) != {"GEOID","LSADC"} or any(x["type"] != "C" for x in wanted.values()):
        raise ValueError("GEOID_LSADC_STRING_FIELDS_REQUIRED")
    rows = []
    for i in range(count):
        start = header_len + i * record_len
        record = data[start:start+record_len]
        if record[:1] != b" ":
            raise ValueError(f"DELETED_OR_INVALID_DBF_RECORD:{i}")
        row = {"source_row": i}
        for name, field in wanted.items():
            raw = record[field["offset"]:field["offset"]+field["width"]]
            text = raw.decode("ascii", errors="strict")
            row[name+"_RAW"] = text
            row[name+"_RAW_HEX"] = raw.hex()
            row[name] = text.rstrip(" ")  # DBF character padding only.
        if not re.fullmatch(r"72[0-9]{8}", row["GEOID"]) or not re.fullmatch(r"[0-9]{2}", row["LSADC"]):
            raise ValueError(f"INVALID_CENSUS_KEY:{i}")
        rows.append(row)
    id_index(rows, "GEOID")
    return rows, {"dbf_record_count":count,"header_len":header_len,"record_len":record_len,"fields":fields,"codepage_mark":data[29],"decoded_fields_encoding":"ASCII (GEOID/LSADC only)","deleted_records":0}


def inspect_archive(path: Path) -> dict:
    data = checked_bytes(path, EXPECTED_SHA256, EXPECTED_SIZE)
    members = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [x.filename for x in archive.infolist()]
        if len(names) != len(set(names)):
            raise ValueError("DUPLICATE_ARCHIVE_MEMBER_PATH")
        for info in archive.infolist():
            name = PurePosixPath(info.filename)
            if name.is_absolute() or ".." in name.parts or "\\" in info.filename or info.flag_bits & 1:
                raise ValueError("UNSAFE_ARCHIVE_MEMBER")
            if info.file_size > 100_000_000:
                raise ValueError("UNEXPECTED_ARCHIVE_MEMBER_SIZE")
            content = archive.read(info)
            members.append({"path":info.filename,"uncompressed_size":len(content),"sha256":digest(content)})
        dbfs = [x for x in names if x.lower().endswith(".dbf")]
        if len(dbfs) != 1:
            raise ValueError("EXPECTED_ONE_DBF")
        rows, schema = parse_dbf(archive.read(dbfs[0]))
    counts = dict(Counter(row["LSADC"] for row in rows))
    return {"state":"PASS" if len(rows)==939 and counts==EXPECTED_LSADC else "FAIL", "claim":"SHA-bound COUSUB GEOID/LSADC census only", "bytes":len(data),"sha256":digest(data),"members":members,"schema":schema,"count":len(rows),"stable_id_count":len(id_index(rows,"GEOID")),"lsadc_counts":counts,"expected_lsadc_counts":EXPECTED_LSADC,"rows":rows}


def compare_rows(a: list[dict], b: list[dict], expected_total: int = 939) -> dict:
    ia = id_index(a,"GEOID"); ib = id_index(b,"GEOID")
    for row in a+b:
        if not isinstance(row.get("LSADC"), str) or not re.fullmatch(r"[0-9]{2}",row["LSADC"]):
            raise ValueError("INVALID_LSADC_COMPARISON_VALUE")
    diff = set_receipt(set(ia),set(ib))
    mismatch = [{"GEOID":k,"a_LSADC":ia[k]["LSADC"],"b_LSADC":ib[k]["LSADC"]} for k in sorted(set(ia)&set(ib)) if ia[k]["LSADC"] != ib[k]["LSADC"]]
    passed = len(ia)==len(ib)==expected_total and not diff["counts"]["symmetric_difference"] and not mismatch
    return {"state":"PASS" if passed else "FAIL","claim":"ID-set and LSADC correspondence; not geometric or byte identity","a_count":len(ia),"b_count":len(ib),"sets":diff,"lsadc_mismatches":mismatch}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--comparison-csv", type=Path)
    parser.add_argument("--comparison-sha256")
    args = parser.parse_args()
    try:
        receipt = inspect_archive(args.archive)
        if args.comparison_csv:
            if receipt["state"] != "PASS":
                raise ValueError("FROZEN_ROWS_MUST_PASS_BEFORE_COMPARISON")
            content = checked_bytes(args.comparison_csv, args.comparison_sha256)
            # Explicit normalized interchange; freeze original TIGERweb HTML/API
            # bytes plus its parse mapping separately, never guess its header.
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
            if reader.fieldnames != ["GEOID","LSADC"]:
                raise ValueError("EXPECTED_EXPLICIT_GEOID_LSADC_CSV_HEADER")
            receipt["comparison"] = compare_rows(receipt["rows"],list(reader))
            receipt["comparison_sha256"] = digest(content)
        write_new(args.out,receipt)
        return 0 if receipt["state"]=="PASS" and receipt.get("comparison",{"state":"PASS"})["state"]=="PASS" else 1
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        write_new(args.out,{"state":"BLOCKED" if isinstance(exc,FileNotFoundError) else "FAIL","error":str(exc),"source_acquisition_performed":False})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
