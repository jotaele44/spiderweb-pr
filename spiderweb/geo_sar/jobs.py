"""Durable job ledger for geographic acquisition and comparison work.

One SQLite file holds every job, its operations, their dependencies, leases,
checkpoints, recorded effects and an append-only event history.  Nothing about
a job lives in a process: a worker, an API server or a conversation can stop
at any point and a later process continues from what the file says.

Rules the ledger enforces:

* **One submit, one job.**  A job is submitted under an idempotency key.  The
  same key with the same specification returns the same job; the same key with
  a different specification is refused.
* **Dependency order.**  An operation is claimable only when everything it
  depends on has succeeded.  A failed dependency blocks its dependants.
* **Leases with fencing.**  A worker claims an operation for a bounded time and
  receives a generation number.  Every later write must present that
  generation; a worker whose lease was taken over can no longer write.
* **Recovery does not repeat a mutation.**  When a lease expires, an operation
  declared ``resumable`` (or one that changes nothing) goes back to the queue
  with its latest checkpoint.  Any other mutating operation stops in
  ``NEEDS_RECONCILIATION`` until a person resolves it.
* **Effects are recorded once.**  ``record_effect`` stores a receipt under a
  key; a second attempt under the same key gets the first receipt back.
* **Authorisation is fixed at submit and fails closed.**  The grant is stored
  with the job and cannot be widened afterwards.  An operation that needs a
  level the grant does not give, or more bytes than it allows, is blocked
  before any handler runs.
* **History is append-only.**  The ``events`` table rejects updates and
  deletes; every checkpoint is also an event, so earlier checkpoints remain
  readable after later ones replace the current value.

The grant vocabulary is the one in
:mod:`spiderweb.access_points.acquisition` (``NONE``, ``METADATA_DISCOVERY``,
``PRODUCT_DOWNLOAD``); :func:`grant_from_authorization` converts that module's
``Authorization``.  This module itself imports only the standard library so a
worker starts without the scientific stack.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

SCHEMA_VERSION = "spiderweb.geo_sar.job_ledger.v1"

LEVEL_NONE = "NONE"
LEVEL_METADATA = "METADATA_DISCOVERY"
LEVEL_PRODUCT = "PRODUCT_DOWNLOAD"
LEVELS = (LEVEL_NONE, LEVEL_METADATA, LEVEL_PRODUCT)

OP_PENDING = "PENDING"
OP_RUNNING = "RUNNING"
OP_SUCCEEDED = "SUCCEEDED"
OP_FAILED = "FAILED"
OP_BLOCKED = "BLOCKED"
OP_NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"
OP_TERMINAL = (OP_SUCCEEDED, OP_FAILED, OP_BLOCKED)

JOB_QUEUED = "QUEUED"
JOB_RUNNING = "RUNNING"
JOB_SUCCEEDED = "SUCCEEDED"
JOB_FAILED = "FAILED"
JOB_BLOCKED = "BLOCKED"
JOB_NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"

_DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    spec_sha256 TEXT NOT NULL,
    grant_json TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS operations (
    op_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    position INTEGER NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    params_json TEXT NOT NULL,
    mutating INTEGER NOT NULL,
    resumable INTEGER NOT NULL,
    required_level TEXT NOT NULL,
    max_attempts INTEGER NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL,
    lease_owner TEXT,
    lease_generation INTEGER NOT NULL DEFAULT 0,
    lease_expires REAL,
    checkpoint_seq INTEGER NOT NULL DEFAULT 0,
    checkpoint_json TEXT,
    result_json TEXT,
    error TEXT,
    UNIQUE (job_id, name)
);
CREATE TABLE IF NOT EXISTS op_deps (
    op_id TEXT NOT NULL REFERENCES operations(op_id),
    depends_on TEXT NOT NULL REFERENCES operations(op_id),
    PRIMARY KEY (op_id, depends_on)
);
CREATE TABLE IF NOT EXISTS effects (
    effect_key TEXT PRIMARY KEY,
    op_id TEXT NOT NULL REFERENCES operations(op_id),
    receipt_json TEXT NOT NULL,
    recorded_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    op_id TEXT,
    ts REAL NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE INDEX IF NOT EXISTS events_job ON events(job_id, seq);
CREATE INDEX IF NOT EXISTS operations_state ON operations(state);
"""


class LedgerError(RuntimeError):
    """Base class for ledger refusals."""


class IdempotencyConflict(LedgerError):
    """The idempotency key is already bound to a different specification."""


class InvalidJob(LedgerError, ValueError):
    """The submitted job is not well formed."""


class StaleLease(LedgerError):
    """The caller's lease was lost, expired or superseded."""


class UnknownJob(LedgerError, KeyError):
    """No such job or operation."""


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """One step of a job.

    ``mutating`` says the step changes something outside the ledger.
    ``resumable`` says an interrupted run of it may be continued from its
    latest checkpoint without repeating a change; only declare it for steps
    built that way (partial file plus atomic rename, effects recorded once).
    """

    name: str
    kind: str
    params: Mapping[str, Any] = field(default_factory=dict)
    depends_on: Sequence[str] = ()
    mutating: bool = False
    resumable: bool = False
    required_level: str = LEVEL_NONE
    max_attempts: int = 3


@dataclass(frozen=True, slots=True)
class Claim:
    """A worker's time-bounded, fenced hold on one operation."""

    op_id: str
    job_id: str
    name: str
    kind: str
    params: dict[str, Any]
    worker_id: str
    generation: int
    attempt: int
    checkpoint: dict[str, Any] | None
    checkpoint_seq: int


def grant_from_authorization(authorization: Any) -> dict[str, Any]:
    """Convert ``spiderweb.access_points.acquisition.Authorization``."""

    return normalise_grant(
        {
            "level": str(getattr(authorization.level, "value", authorization.level)),
            "granted_by": authorization.granted_by,
            "max_requests": authorization.max_requests,
            "max_bytes": authorization.max_bytes,
        }
    )


def normalise_grant(grant: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate a grant.  ``None`` and ``{}`` grant nothing."""

    raw = dict(grant or {})
    unknown = set(raw) - {"level", "granted_by", "max_requests", "max_bytes"}
    if unknown:
        raise InvalidJob(f"unknown grant fields: {sorted(unknown)}")
    level = raw.get("level", LEVEL_NONE)
    if level not in LEVELS:
        raise InvalidJob(f"unknown authorisation level: {level!r}")
    granted_by = str(raw.get("granted_by", "")).strip()
    max_requests = int(raw.get("max_requests", 0))
    max_bytes = int(raw.get("max_bytes", 0))
    if max_requests < 0 or max_bytes < 0:
        raise InvalidJob("grant bounds cannot be negative")
    if level != LEVEL_NONE:
        if not granted_by:
            raise InvalidJob("a grant must name who authorised it")
        if max_requests < 1:
            raise InvalidJob("a grant must bound the number of requests")
    if level == LEVEL_PRODUCT and max_bytes < 1:
        raise InvalidJob("a product grant must bound the number of bytes")
    if level != LEVEL_PRODUCT and max_bytes:
        raise InvalidJob("only a product grant carries a byte ceiling")
    return {
        "level": level,
        "granted_by": granted_by,
        "max_requests": max_requests,
        "max_bytes": max_bytes,
    }


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _validate_specs(operations: Sequence[OperationSpec]) -> None:
    if not operations:
        raise InvalidJob("a job needs at least one operation")
    names = [op.name for op in operations]
    if len(set(names)) != len(names):
        raise InvalidJob("operation names must be unique within a job")
    known = set(names)
    for op in operations:
        if not op.name or not op.kind:
            raise InvalidJob("an operation needs a name and a kind")
        if op.required_level not in LEVELS:
            raise InvalidJob(f"unknown authorisation level: {op.required_level!r}")
        if op.max_attempts < 1:
            raise InvalidJob("max_attempts must be at least 1")
        if op.resumable and not op.mutating:
            raise InvalidJob("only a mutating operation is declared resumable")
        missing = set(op.depends_on) - known
        if missing:
            raise InvalidJob(f"{op.name} depends on unknown {sorted(missing)}")
        if op.name in op.depends_on:
            raise InvalidJob(f"{op.name} depends on itself")
    # Kahn's algorithm: a job whose operations cannot be ordered is refused.
    remaining = {op.name: set(op.depends_on) for op in operations}
    while remaining:
        ready = [name for name, deps in remaining.items() if not deps]
        if not ready:
            raise InvalidJob("operation dependencies form a cycle")
        for name in ready:
            del remaining[name]
        for deps in remaining.values():
            deps.difference_update(ready)


class JobLedger:
    """A connection to one ledger file.  Open one per process or thread."""

    def __init__(self, path: str | Path, *, busy_timeout_s: float = 30.0) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(
            self.path, timeout=busy_timeout_s, isolation_level=None
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA foreign_keys=ON")
        with self._tx():
            for statement in _split_ddl(_DDL):
                self._db.execute(statement)
            self._db.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
                (SCHEMA_VERSION,),
            )
        found = self._db.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()["value"]
        if found != SCHEMA_VERSION:
            raise LedgerError(
                f"ledger schema {found!r} is not {SCHEMA_VERSION!r}; refusing to open"
            )

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "JobLedger":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- transactions ------------------------------------------------------

    def _tx(self) -> "_Transaction":
        return _Transaction(self._db)

    def _event(
        self, job_id: str, op_id: str | None, type_: str, payload: Mapping[str, Any]
    ) -> int:
        cursor = self._db.execute(
            "INSERT INTO events(job_id, op_id, ts, type, payload_json) VALUES (?,?,?,?,?)",
            (job_id, op_id, time.time(), type_, _canonical(dict(payload))),
        )
        return int(cursor.lastrowid or 0)

    # -- submit ------------------------------------------------------------

    def submit(
        self,
        *,
        kind: str,
        operations: Sequence[OperationSpec],
        idempotency_key: str,
        grant: Mapping[str, Any] | None = None,
    ) -> str:
        """Record a job and return its identity.  Safe to repeat."""

        if not kind or not idempotency_key:
            raise InvalidJob("a job needs a kind and an idempotency key")
        _validate_specs(operations)
        stored_grant = normalise_grant(grant)
        spec = {
            "kind": kind,
            "grant": stored_grant,
            "operations": [
                {
                    "name": op.name,
                    "kind": op.kind,
                    "params": dict(op.params),
                    "depends_on": sorted(op.depends_on),
                    "mutating": bool(op.mutating),
                    "resumable": bool(op.resumable),
                    "required_level": op.required_level,
                    "max_attempts": int(op.max_attempts),
                }
                for op in operations
            ],
        }
        spec_sha = hashlib.sha256(_canonical(spec).encode()).hexdigest()
        now = time.time()
        with self._tx():
            existing = self._db.execute(
                "SELECT job_id, spec_sha256 FROM jobs WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                if existing["spec_sha256"] != spec_sha:
                    raise IdempotencyConflict(
                        f"idempotency key {idempotency_key!r} is bound to a "
                        "different job specification"
                    )
                return str(existing["job_id"])
            job_id = f"geosar-job-{uuid.uuid4().hex}"
            self._db.execute(
                "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    kind,
                    idempotency_key,
                    spec_sha,
                    _canonical(stored_grant),
                    JOB_QUEUED,
                    now,
                    now,
                ),
            )
            op_ids: dict[str, str] = {}
            for position, op in enumerate(operations):
                op_id = f"{job_id}:op:{position:04d}"
                op_ids[op.name] = op_id
                self._db.execute(
                    "INSERT INTO operations(op_id, job_id, position, name, kind, "
                    "params_json, mutating, resumable, required_level, max_attempts, "
                    "state) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        op_id,
                        job_id,
                        position,
                        op.name,
                        op.kind,
                        _canonical(dict(op.params)),
                        int(op.mutating),
                        int(op.resumable),
                        op.required_level,
                        int(op.max_attempts),
                        OP_PENDING,
                    ),
                )
            for op in operations:
                for dependency in op.depends_on:
                    self._db.execute(
                        "INSERT INTO op_deps VALUES (?,?)",
                        (op_ids[op.name], op_ids[dependency]),
                    )
            self._event(
                job_id,
                None,
                "JOB_SUBMITTED",
                {
                    "kind": kind,
                    "spec_sha256": spec_sha,
                    "operations": len(operations),
                    "grant_level": stored_grant["level"],
                },
            )
            return job_id

    # -- claim -------------------------------------------------------------

    def claim(
        self, worker_id: str, *, lease_seconds: float, now: float | None = None
    ) -> Claim | None:
        """Take the next runnable operation, or return ``None``.

        Expired leases are reconciled first, inside the same transaction, so a
        worker never takes work whose previous holder might still write.
        """

        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        moment = time.time() if now is None else now
        with self._tx():
            self._reconcile_expired(moment)
            while True:
                row = self._db.execute(
                    "SELECT o.* FROM operations o WHERE o.state=? AND NOT EXISTS ("
                    " SELECT 1 FROM op_deps d JOIN operations p ON p.op_id=d.depends_on"
                    " WHERE d.op_id=o.op_id AND p.state<>?)"
                    " ORDER BY o.job_id, o.position LIMIT 1",
                    (OP_PENDING, OP_SUCCEEDED),
                ).fetchone()
                if row is None:
                    return None
                refusal = self._authorisation_refusal(row)
                if refusal is not None:
                    self._finish(
                        row, OP_BLOCKED, error=refusal, event="AUTHORIZATION_DENIED"
                    )
                    continue
                if row["attempts"] >= row["max_attempts"]:
                    self._finish(
                        row,
                        OP_FAILED,
                        error=row["error"] or "retry limit reached",
                        event="OP_FAILED",
                    )
                    continue
                generation = int(row["lease_generation"]) + 1
                attempt = int(row["attempts"]) + 1
                self._db.execute(
                    "UPDATE operations SET state=?, lease_owner=?, lease_generation=?,"
                    " lease_expires=?, attempts=? WHERE op_id=?",
                    (
                        OP_RUNNING,
                        worker_id,
                        generation,
                        moment + lease_seconds,
                        attempt,
                        row["op_id"],
                    ),
                )
                checkpoint = (
                    json.loads(row["checkpoint_json"])
                    if row["checkpoint_json"]
                    else None
                )
                self._event(
                    row["job_id"],
                    row["op_id"],
                    "OP_CLAIMED",
                    {
                        "worker_id": worker_id,
                        "generation": generation,
                        "attempt": attempt,
                        "resumed_from_checkpoint_seq": int(row["checkpoint_seq"]),
                    },
                )
                self._refresh_job(row["job_id"])
                return Claim(
                    op_id=row["op_id"],
                    job_id=row["job_id"],
                    name=row["name"],
                    kind=row["kind"],
                    params=json.loads(row["params_json"]),
                    worker_id=worker_id,
                    generation=generation,
                    attempt=attempt,
                    checkpoint=checkpoint,
                    checkpoint_seq=int(row["checkpoint_seq"]),
                )

    def _authorisation_refusal(self, row: sqlite3.Row) -> str | None:
        required = row["required_level"]
        if required == LEVEL_NONE:
            return None
        grant = json.loads(
            self._db.execute(
                "SELECT grant_json FROM jobs WHERE job_id=?", (row["job_id"],)
            ).fetchone()["grant_json"]
        )
        if grant["level"] != required:
            return f"{required} is not authorised (grant is {grant['level']})"
        if required == LEVEL_PRODUCT:
            expected = json.loads(row["params_json"]).get("expected_bytes")
            if not isinstance(expected, int) or isinstance(expected, bool):
                return "a product operation must declare expected_bytes"
            spent = self._db.execute(
                "SELECT COALESCE(SUM(json_extract(params_json,'$.expected_bytes')),0)"
                " AS total, COUNT(*) AS files FROM operations WHERE job_id=?"
                " AND required_level=? AND state IN (?,?) AND op_id<>?",
                (row["job_id"], LEVEL_PRODUCT, OP_RUNNING, OP_SUCCEEDED, row["op_id"]),
            ).fetchone()
            if spent["total"] + expected > grant["max_bytes"]:
                return (
                    f"byte ceiling of {grant['max_bytes']} would be exceeded "
                    f"({spent['total']} committed, {expected} requested)"
                )
            if spent["files"] + 1 > grant["max_requests"]:
                return f"file budget of {grant['max_requests']} is exhausted"
        return None

    # -- writes under a lease ---------------------------------------------

    def _held(self, claim: Claim, moment: float) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT * FROM operations WHERE op_id=?", (claim.op_id,)
        ).fetchone()
        if row is None:
            raise UnknownJob(claim.op_id)
        if (
            row["state"] != OP_RUNNING
            or row["lease_owner"] != claim.worker_id
            or int(row["lease_generation"]) != claim.generation
        ):
            raise StaleLease(
                f"{claim.op_id}: lease generation {claim.generation} held by "
                f"{claim.worker_id} is no longer current"
            )
        if row["lease_expires"] is not None and row["lease_expires"] < moment:
            raise StaleLease(f"{claim.op_id}: lease expired")
        return row

    def heartbeat(
        self, claim: Claim, *, lease_seconds: float, now: float | None = None
    ) -> None:
        moment = time.time() if now is None else now
        with self._tx():
            self._held(claim, moment)
            self._db.execute(
                "UPDATE operations SET lease_expires=? WHERE op_id=?",
                (moment + lease_seconds, claim.op_id),
            )

    def checkpoint(
        self,
        claim: Claim,
        data: Mapping[str, Any],
        *,
        lease_seconds: float,
        now: float | None = None,
    ) -> int:
        """Store progress, extend the lease, and return the checkpoint number."""

        moment = time.time() if now is None else now
        with self._tx():
            row = self._held(claim, moment)
            seq = int(row["checkpoint_seq"]) + 1
            self._db.execute(
                "UPDATE operations SET checkpoint_seq=?, checkpoint_json=?,"
                " lease_expires=? WHERE op_id=?",
                (seq, _canonical(dict(data)), moment + lease_seconds, claim.op_id),
            )
            self._event(
                claim.job_id,
                claim.op_id,
                "CHECKPOINT",
                {
                    "checkpoint_seq": seq,
                    "generation": claim.generation,
                    "data": dict(data),
                },
            )
            return seq

    def note(self, claim: Claim, type_: str, payload: Mapping[str, Any]) -> int:
        """Append a handler-defined event under a current lease."""

        with self._tx():
            self._held(claim, time.time())
            return self._event(claim.job_id, claim.op_id, type_, payload)

    def record_effect(
        self, claim: Claim, effect_key: str, receipt: Mapping[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        """Record an outside change once.  Returns ``(receipt, created)``."""

        with self._tx():
            self._held(claim, time.time())
            existing = self._db.execute(
                "SELECT receipt_json, op_id FROM effects WHERE effect_key=?",
                (effect_key,),
            ).fetchone()
            if existing is not None:
                self._event(
                    claim.job_id,
                    claim.op_id,
                    "EFFECT_REUSED",
                    {"effect_key": effect_key, "first_op_id": existing["op_id"]},
                )
                return json.loads(existing["receipt_json"]), False
            self._db.execute(
                "INSERT INTO effects VALUES (?,?,?,?)",
                (effect_key, claim.op_id, _canonical(dict(receipt)), time.time()),
            )
            self._event(
                claim.job_id,
                claim.op_id,
                "EFFECT_RECORDED",
                {"effect_key": effect_key},
            )
            return dict(receipt), True

    def lookup_effect(self, effect_key: str) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT receipt_json FROM effects WHERE effect_key=?", (effect_key,)
        ).fetchone()
        return json.loads(row["receipt_json"]) if row else None

    def complete(self, claim: Claim, result: Mapping[str, Any] | None = None) -> None:
        with self._tx():
            row = self._held(claim, time.time())
            self._finish(
                row, OP_SUCCEEDED, result=dict(result or {}), event="OP_SUCCEEDED"
            )

    def fail(self, claim: Claim, error: str, *, retryable: bool = True) -> str:
        """Report a failed attempt.  Returns the operation's new state."""

        with self._tx():
            row = self._held(claim, time.time())
            exhausted = int(row["attempts"]) >= int(row["max_attempts"])
            if retryable and not exhausted:
                self._db.execute(
                    "UPDATE operations SET state=?, lease_owner=NULL,"
                    " lease_expires=NULL, error=? WHERE op_id=?",
                    (OP_PENDING, error, claim.op_id),
                )
                self._event(
                    claim.job_id,
                    claim.op_id,
                    "OP_ATTEMPT_FAILED",
                    {"attempt": int(row["attempts"]), "error": error},
                )
                self._refresh_job(claim.job_id)
                return OP_PENDING
            self._finish(row, OP_FAILED, error=error, event="OP_FAILED")
            return OP_FAILED

    def _finish(
        self,
        row: sqlite3.Row,
        state: str,
        *,
        event: str,
        result: Mapping[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self._db.execute(
            "UPDATE operations SET state=?, lease_owner=NULL, lease_expires=NULL,"
            " result_json=?, error=? WHERE op_id=?",
            (
                state,
                _canonical(dict(result)) if result is not None else row["result_json"],
                error,
                row["op_id"],
            ),
        )
        payload: dict[str, Any] = {"attempts": int(row["attempts"])}
        if error is not None:
            payload["error"] = error
        if result is not None:
            payload["result"] = dict(result)
        self._event(row["job_id"], row["op_id"], event, payload)
        if state in (OP_FAILED, OP_BLOCKED):
            self._block_dependants(row["job_id"], row["op_id"], row["name"])
        self._refresh_job(row["job_id"])

    def _block_dependants(self, job_id: str, op_id: str, name: str) -> None:
        frontier = [(op_id, name)]
        while frontier:
            current, current_name = frontier.pop()
            for dependant in self._db.execute(
                "SELECT o.op_id, o.name FROM op_deps d JOIN operations o"
                " ON o.op_id=d.op_id WHERE d.depends_on=? AND o.state=?",
                (current, OP_PENDING),
            ).fetchall():
                reason = f"dependency {current_name} did not succeed"
                self._db.execute(
                    "UPDATE operations SET state=?, error=? WHERE op_id=?",
                    (OP_BLOCKED, reason, dependant["op_id"]),
                )
                self._event(job_id, dependant["op_id"], "OP_BLOCKED", {"error": reason})
                frontier.append((dependant["op_id"], dependant["name"]))

    # -- recovery ----------------------------------------------------------

    def reconcile_expired(self, now: float | None = None) -> list[str]:
        """Release or stop operations whose lease ran out."""

        with self._tx():
            return self._reconcile_expired(time.time() if now is None else now)

    def _reconcile_expired(self, moment: float) -> list[str]:
        touched: list[str] = []
        for row in self._db.execute(
            "SELECT * FROM operations WHERE state=? AND lease_expires<?",
            (OP_RUNNING, moment),
        ).fetchall():
            touched.append(row["op_id"])
            safe = (not row["mutating"]) or bool(row["resumable"])
            new_state = OP_PENDING if safe else OP_NEEDS_RECONCILIATION
            self._db.execute(
                "UPDATE operations SET state=?, lease_owner=NULL, lease_expires=NULL"
                " WHERE op_id=?",
                (new_state, row["op_id"]),
            )
            self._event(
                row["job_id"],
                row["op_id"],
                "LEASE_EXPIRED",
                {
                    "worker_id": row["lease_owner"],
                    "generation": int(row["lease_generation"]),
                    "new_state": new_state,
                    "checkpoint_seq": int(row["checkpoint_seq"]),
                },
            )
            self._refresh_job(row["job_id"])
        return touched

    def resolve_reconciliation(
        self, op_id: str, *, outcome: str, resolved_by: str, note: str
    ) -> None:
        """A person decides what an interrupted, non-resumable change did.

        ``outcome`` is ``RETRY`` (it did not happen; run it again),
        ``SUCCEEDED`` (it happened completely) or ``FAILED``.
        """

        if outcome not in ("RETRY", OP_SUCCEEDED, OP_FAILED):
            raise ValueError(f"unknown outcome {outcome!r}")
        if not resolved_by.strip() or not note.strip():
            raise ValueError("a resolution names who decided and why")
        with self._tx():
            row = self._db.execute(
                "SELECT * FROM operations WHERE op_id=?", (op_id,)
            ).fetchone()
            if row is None:
                raise UnknownJob(op_id)
            if row["state"] != OP_NEEDS_RECONCILIATION:
                raise LedgerError(f"{op_id} is {row['state']}, not awaiting a decision")
            self._event(
                row["job_id"],
                op_id,
                "RECONCILIATION_RESOLVED",
                {"outcome": outcome, "resolved_by": resolved_by, "note": note},
            )
            if outcome == "RETRY":
                self._db.execute(
                    "UPDATE operations SET state=? WHERE op_id=?", (OP_PENDING, op_id)
                )
                self._refresh_job(row["job_id"])
            else:
                self._finish(
                    row,
                    outcome,
                    event=f"OP_{outcome}",
                    result={} if outcome == OP_SUCCEEDED else None,
                    error=None if outcome == OP_SUCCEEDED else note,
                )

    def _refresh_job(self, job_id: str) -> None:
        states = [
            r["state"]
            for r in self._db.execute(
                "SELECT state FROM operations WHERE job_id=?", (job_id,)
            ).fetchall()
        ]
        if any(s == OP_FAILED for s in states):
            # A failure is terminal for the job once nothing else can move.
            moving = any(s in (OP_PENDING, OP_RUNNING) for s in states)
            new = JOB_RUNNING if moving else JOB_FAILED
        elif any(s == OP_NEEDS_RECONCILIATION for s in states):
            new = JOB_NEEDS_RECONCILIATION
        elif all(s == OP_SUCCEEDED for s in states):
            new = JOB_SUCCEEDED
        elif any(s == OP_RUNNING for s in states) or any(
            s == OP_SUCCEEDED for s in states
        ):
            moving = any(s in (OP_PENDING, OP_RUNNING) for s in states)
            new = JOB_RUNNING if moving else JOB_BLOCKED
        elif all(s == OP_PENDING for s in states):
            new = JOB_QUEUED
        elif any(s == OP_PENDING for s in states):
            new = JOB_RUNNING
        else:
            new = JOB_BLOCKED
        current = self._db.execute(
            "SELECT state FROM jobs WHERE job_id=?", (job_id,)
        ).fetchone()["state"]
        if current != new:
            self._db.execute(
                "UPDATE jobs SET state=?, updated_at=? WHERE job_id=?",
                (new, time.time(), job_id),
            )
            self._event(job_id, None, "JOB_STATE", {"from": current, "to": new})

    # -- reads (what a later session reconnects through) ------------------

    def find_job(self, idempotency_key: str) -> str | None:
        row = self._db.execute(
            "SELECT job_id FROM jobs WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        return str(row["job_id"]) if row else None

    def job(self, job_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise UnknownJob(job_id)
        operations = []
        for op in self._db.execute(
            "SELECT * FROM operations WHERE job_id=? ORDER BY position", (job_id,)
        ).fetchall():
            operations.append(
                {
                    "op_id": op["op_id"],
                    "name": op["name"],
                    "kind": op["kind"],
                    "state": op["state"],
                    "attempts": int(op["attempts"]),
                    "max_attempts": int(op["max_attempts"]),
                    "mutating": bool(op["mutating"]),
                    "resumable": bool(op["resumable"]),
                    "required_level": op["required_level"],
                    "lease_owner": op["lease_owner"],
                    "lease_generation": int(op["lease_generation"]),
                    "checkpoint_seq": int(op["checkpoint_seq"]),
                    "checkpoint": json.loads(op["checkpoint_json"])
                    if op["checkpoint_json"]
                    else None,
                    "result": json.loads(op["result_json"])
                    if op["result_json"]
                    else None,
                    "error": op["error"],
                }
            )
        return {
            "job_id": row["job_id"],
            "kind": row["kind"],
            "idempotency_key": row["idempotency_key"],
            "state": row["state"],
            "grant": json.loads(row["grant_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "operations": operations,
        }

    def events(self, job_id: str, *, after_seq: int = 0) -> list[dict[str, Any]]:
        """Events for a job after a cursor, oldest first."""

        return [
            {
                "seq": int(r["seq"]),
                "job_id": r["job_id"],
                "op_id": r["op_id"],
                "ts": r["ts"],
                "type": r["type"],
                "payload": json.loads(r["payload_json"]),
            }
            for r in self._db.execute(
                "SELECT * FROM events WHERE job_id=? AND seq>? ORDER BY seq",
                (job_id, after_seq),
            ).fetchall()
        ]

    def has_work(self) -> bool:
        """True while an operation is running or could be claimed.

        A pending operation waiting on one that needs a person's decision is
        not work a worker can do, so it does not keep a worker alive.
        """

        row = self._db.execute(
            "SELECT 1 FROM operations o WHERE o.state=? OR (o.state=? AND NOT EXISTS ("
            " SELECT 1 FROM op_deps d JOIN operations p ON p.op_id=d.depends_on"
            " WHERE d.op_id=o.op_id AND p.state<>?)) LIMIT 1",
            (OP_RUNNING, OP_PENDING, OP_SUCCEEDED),
        ).fetchone()
        return row is not None


def _split_ddl(ddl: str) -> Iterator[str]:
    """Yield statements; triggers contain ``;`` so split with the parser."""

    buffer = ""
    for line in ddl.splitlines():
        buffer += line + "\n"
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            buffer = ""
            if statement:
                yield statement


class _Transaction:
    """``BEGIN IMMEDIATE`` ... ``COMMIT``; any exception rolls back."""

    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db

    def __enter__(self) -> None:
        self._db.execute("BEGIN IMMEDIATE")

    def __exit__(self, exc_type: object, *rest: object) -> None:
        if exc_type is None:
            self._db.execute("COMMIT")
        else:
            self._db.execute("ROLLBACK")
