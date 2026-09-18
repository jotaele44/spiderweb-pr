"""Byte/logical/archive manifestation adjudication without name-only identity."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import tarfile
import zipfile

BYTE_IDENTICAL = "BYTE_IDENTICAL"
PURE_RECOMPRESSION = "PURE_RECOMPRESSION"
SAME_PAYLOADS_DIFFERENT_PATHS = "SAME_PAYLOADS_DIFFERENT_PATHS"
DISTINCT_PAYLOADS = "DISTINCT_PAYLOADS"
UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class MemberIdentity:
    path: str
    uncompressed_size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ManifestationComparison:
    path_a: str
    path_b: str
    byte_sha256_a: str | None
    byte_sha256_b: str | None
    classification: str
    members_a: tuple[MemberIdentity, ...] = ()
    members_b: tuple[MemberIdentity, ...] = ()

    def as_dict(self):
        return asdict(self)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _members(path: Path) -> tuple[MemberIdentity, ...] | None:
    rows: list[MemberIdentity] = []
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if not info.is_dir():
                        data = archive.read(info)
                        rows.append(MemberIdentity(info.filename, len(data), _sha(data)))
        elif tarfile.is_tarfile(path):
            with tarfile.open(path) as archive:
                for info in archive.getmembers():
                    if info.isfile():
                        handle = archive.extractfile(info)
                        if handle is None: return None
                        data = handle.read()
                        rows.append(MemberIdentity(info.name, len(data), _sha(data)))
        else:
            return ()
    except (OSError, tarfile.TarError, zipfile.BadZipFile):
        return None
    return tuple(sorted(rows, key=lambda item: item.path))


def compare_manifestations(path_a: str | Path, path_b: str | Path) -> ManifestationComparison:
    a, b = Path(path_a), Path(path_b)
    if not a.is_file() or not b.is_file():
        return ManifestationComparison(str(a), str(b), None, None, UNRESOLVED)
    bytes_a, bytes_b = a.read_bytes(), b.read_bytes()
    hash_a, hash_b = _sha(bytes_a), _sha(bytes_b)
    members_a, members_b = _members(a), _members(b)
    if members_a is None or members_b is None:
        return ManifestationComparison(str(a), str(b), hash_a, hash_b, UNRESOLVED)
    if hash_a == hash_b:
        state = BYTE_IDENTICAL
    elif members_a and members_b:
        exact_a = {(m.path, m.uncompressed_size, m.sha256) for m in members_a}
        exact_b = {(m.path, m.uncompressed_size, m.sha256) for m in members_b}
        payload_a = Counter((m.uncompressed_size, m.sha256) for m in members_a)
        payload_b = Counter((m.uncompressed_size, m.sha256) for m in members_b)
        if exact_a == exact_b: state = PURE_RECOMPRESSION
        elif payload_a == payload_b: state = SAME_PAYLOADS_DIFFERENT_PATHS
        else: state = DISTINCT_PAYLOADS
    else:
        state = DISTINCT_PAYLOADS
    return ManifestationComparison(str(a), str(b), hash_a, hash_b, state, members_a, members_b)
