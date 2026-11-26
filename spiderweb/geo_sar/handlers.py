"""Operation handlers the job worker can run.

Preparation stage: every handler here is local.  None of them opens a network
connection.  ``local_copy`` exists to exercise the retrieval contract --
partial file, verified checkpoint, checksum, atomic rename, one recorded
effect per artifact -- against a file on disk, so that the durability tests
measure the ledger and not a provider.  Provider retrieval is an
implementation-stage handler and will reuse
``spiderweb.access_points.products.DownloadSession``.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from pipeline.path_safety import safe_join

from .jobs import Claim, JobLedger


class HandlerError(RuntimeError):
    """A handler failed.  ``retryable`` says whether another attempt can help."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class Context:
    ledger: JobLedger
    claim: Claim
    artifact_root: Path
    lease_seconds: float


Handler = Callable[[Context], Mapping[str, Any]]


def noop(context: Context) -> Mapping[str, Any]:
    return {"echo": context.claim.params.get("echo")}


def always_fail(context: Context) -> Mapping[str, Any]:
    raise HandlerError(
        str(context.claim.params.get("message", "declared failure")),
        retryable=bool(context.claim.params.get("retryable", True)),
    )


def sleep(context: Context) -> Mapping[str, Any]:
    """Hold the lease without checkpointing.  Used to test lease expiry."""

    time.sleep(float(context.claim.params.get("seconds", 0)))
    return {}


def _prefix_sha256(path: Path, length: int) -> str | None:
    digest = hashlib.sha256()
    remaining = length
    try:
        with path.open("rb") as handle:
            while remaining:
                block = handle.read(min(1 << 20, remaining))
                if not block:
                    return None
                digest.update(block)
                remaining -= len(block)
    except FileNotFoundError:
        return None
    return digest.hexdigest()


def local_copy(context: Context) -> Mapping[str, Any]:
    """Copy a local file into the artifact root as retrieval would.

    params: ``source`` (path), ``dest`` (path relative to the artifact root),
    ``expected_sha256``, ``expected_bytes``, optional ``chunk_bytes`` and
    ``chunk_delay_s``.

    A checkpoint records the byte offset reached and the SHA-256 of the bytes
    before it, after those bytes are flushed to disk.  On resume the partial
    file is re-hashed up to the checkpoint offset; only if that matches is the
    copy continued from there.  Otherwise the checkpoint is rejected and the
    copy starts again from zero.
    """

    claim, ledger = context.claim, context.ledger
    params = claim.params
    source = Path(params["source"])
    expected_sha = str(params["expected_sha256"])
    expected_bytes = int(params["expected_bytes"])
    chunk = int(params.get("chunk_bytes", 1 << 20))
    delay = float(params.get("chunk_delay_s", 0))
    dest = safe_join(context.artifact_root, str(params["dest"]))
    effect_key = f"artifact:sha256:{expected_sha}"

    recorded = ledger.lookup_effect(effect_key)
    if recorded is not None and Path(recorded["path"]).is_file():
        receipt, _ = ledger.record_effect(claim, effect_key, recorded)
        return {"reused": True, "bytes_written_this_attempt": 0, **receipt}

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")

    offset = 0
    digest = hashlib.sha256()
    checkpoint = claim.checkpoint
    if checkpoint:
        claimed = int(checkpoint.get("offset", 0))
        if claimed and _prefix_sha256(part, claimed) == checkpoint.get("prefix_sha256"):
            offset = claimed
            with part.open("rb") as handle:
                remaining = offset
                while remaining:
                    block = handle.read(min(1 << 20, remaining))
                    digest.update(block)
                    remaining -= len(block)
        elif claimed:
            ledger.note(
                claim,
                "CHECKPOINT_REJECTED",
                {"checkpoint_seq": claim.checkpoint_seq, "offset": claimed},
            )
    ledger.note(
        claim,
        "RETRIEVAL_STARTED",
        {
            "start_offset": offset,
            "from_checkpoint_seq": claim.checkpoint_seq if offset else 0,
        },
    )

    written = 0
    with source.open("rb") as reader, part.open("r+b" if offset else "wb") as writer:
        reader.seek(offset)
        writer.seek(offset)
        writer.truncate(offset)
        while True:
            block = reader.read(chunk)
            if not block:
                break
            if offset + len(block) > expected_bytes:
                raise HandlerError(
                    "source is larger than expected_bytes", retryable=False
                )
            writer.write(block)
            writer.flush()
            os.fsync(writer.fileno())
            digest.update(block)
            offset += len(block)
            written += len(block)
            ledger.checkpoint(
                claim,
                {"offset": offset, "prefix_sha256": digest.copy().hexdigest()},
                lease_seconds=context.lease_seconds,
            )
            if delay:
                time.sleep(delay)

    computed = digest.hexdigest()
    if offset != expected_bytes or computed != expected_sha:
        part.unlink(missing_ok=True)
        raise HandlerError(
            f"integrity check failed: {offset} bytes, sha256 {computed}",
            retryable=False,
        )
    os.replace(part, dest)
    receipt, created = ledger.record_effect(
        claim,
        effect_key,
        {"path": str(dest), "sha256": computed, "bytes": offset},
    )
    return {"reused": not created, "bytes_written_this_attempt": written, **receipt}


HANDLERS: dict[str, Handler] = {
    "noop": noop,
    "always_fail": always_fail,
    "sleep": sleep,
    "local_copy": local_copy,
}
