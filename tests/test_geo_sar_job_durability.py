"""Durability qualification for the geographic job ledger (FED-GEO-SAR-001 §19).

Each of the ten mandatory durability tests is one test function, numbered as
in the directive.  Workers are real, separate operating-system processes and
interruption is ``SIGKILL``; nothing here simulates a restart by calling a
function.  No test uses the network: retrieval is exercised with
``local_copy`` against a file on disk.

What this does not cover is written in ``docs/geo_sar/D16_DURABILITY_RECEIPT.md``.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from spiderweb.geo_sar.jobs import (
    JOB_BLOCKED,
    JOB_FAILED,
    JOB_NEEDS_RECONCILIATION,
    JOB_SUCCEEDED,
    LEVEL_PRODUCT,
    OP_BLOCKED,
    OP_FAILED,
    OP_NEEDS_RECONCILIATION,
    OP_PENDING,
    OP_SUCCEEDED,
    IdempotencyConflict,
    InvalidJob,
    JobLedger,
    OperationSpec,
    StaleLease,
)

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="process-kill durability tests need POSIX signals"
)

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER = REPO_ROOT / "scripts" / "geo_sar_worker.py"
CHUNK = 16 * 1024
CHUNKS = 60
TIMEOUT = 60.0


# -- helpers ---------------------------------------------------------------


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _spawn_worker(db: Path, root: Path, worker_id: str, *, lease: float = 1.0):
    return subprocess.Popen(
        [
            sys.executable,
            str(WORKER),
            "--db",
            str(db),
            "--artifact-root",
            str(root),
            "--worker-id",
            worker_id,
            "--lease-seconds",
            str(lease),
            "--poll-seconds",
            "0.05",
            "--until-idle",
        ],
        env=_env(),
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _finish(process: subprocess.Popen) -> None:
    try:
        _, stderr = process.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise AssertionError("worker did not stop")
    assert process.returncode == 0, stderr.decode(errors="replace")


def _wait(predicate, what: str, timeout: float = TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {what}")


def _source(tmp_path: Path) -> tuple[Path, str, int]:
    data = b"".join(
        hashlib.sha256(i.to_bytes(4, "big")).digest() * (CHUNK // 32)
        for i in range(CHUNKS)
    )
    path = tmp_path / "provider" / "USGS_1M_fixture.tif"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest(), len(data)


def _copy_op(source: tuple[Path, str, int], *, delay: float, name="retrieve", **extra):
    path, sha, size = source
    return OperationSpec(
        name=name,
        kind="local_copy",
        params={
            "source": str(path),
            "dest": f"originals/{sha[:16]}/USGS_1M_fixture.tif",
            "expected_sha256": sha,
            "expected_bytes": size,
            "chunk_bytes": CHUNK,
            "chunk_delay_s": delay,
        },
        mutating=True,
        resumable=True,
        **extra,
    )


def _types(ledger: JobLedger, job_id: str) -> list[str]:
    return [event["type"] for event in ledger.events(job_id)]


def _checkpoints(db: Path, job_id: str) -> list[dict]:
    with JobLedger(db) as ledger:
        return [e for e in ledger.events(job_id) if e["type"] == "CHECKPOINT"]


def _kill_mid_copy(db: Path, root: Path, job_id: str, *, at_least: int = 4) -> dict:
    """Start a worker, kill it after some checkpoints, return the last one."""

    worker = _spawn_worker(db, root, "worker-a")
    try:
        _wait(lambda: len(_checkpoints(db, job_id)) >= at_least, "checkpoints")
    finally:
        os.killpg(worker.pid, signal.SIGKILL)
        worker.wait()
    last = _checkpoints(db, job_id)[-1]
    assert last["payload"]["data"]["offset"] < CHUNK * CHUNKS, "killed too late"
    return last


@pytest.fixture()
def paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "ledger" / "jobs.sqlite", tmp_path / "artifacts"


# -- 01 --------------------------------------------------------------------


def test_01_execution_survives_conversation_termination(tmp_path, paths):
    """The process that submits a job exits; the job still runs to the end."""

    db, root = paths
    source = _source(tmp_path)
    submit = (
        "import sys, json\n"
        "from spiderweb.geo_sar.jobs import JobLedger, OperationSpec\n"
        "spec = json.loads(sys.argv[2])\n"
        "with JobLedger(sys.argv[1]) as ledger:\n"
        "    print(ledger.submit(kind='acquisition', idempotency_key='conv-1',\n"
        "        operations=[OperationSpec(name='retrieve', kind='local_copy',\n"
        "            params=spec, mutating=True, resumable=True)]))\n"
    )
    params = _copy_op(source, delay=0).params
    done = subprocess.run(
        [sys.executable, "-c", submit, str(db), json.dumps(dict(params))],
        env=_env(),
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=True,
    )
    job_id = done.stdout.strip()

    # The submitting "session" is gone.  Nothing is running.
    with JobLedger(db) as ledger:
        assert ledger.job(job_id)["state"] == "QUEUED"

    _finish(_spawn_worker(db, root, "worker-a"))
    with JobLedger(db) as ledger:
        job = ledger.job(job_id)
    assert job["state"] == JOB_SUCCEEDED
    assert (
        hashlib.sha256(
            Path(job["operations"][0]["result"]["path"]).read_bytes()
        ).hexdigest()
        == source[1]
    )


# -- 02 --------------------------------------------------------------------


def test_02_execution_survives_frontend_disconnection(tmp_path, paths):
    """A client following the job's events is killed; the worker is unaffected."""

    db, root = paths
    source = _source(tmp_path)
    with JobLedger(db) as ledger:
        job_id = ledger.submit(
            kind="acquisition",
            idempotency_key="fe-1",
            operations=[_copy_op(source, delay=0.02)],
        )
    follower_code = (
        "import sys, time\n"
        "from spiderweb.geo_sar.jobs import JobLedger\n"
        "ledger = JobLedger(sys.argv[1]); cursor = 0\n"
        "while True:\n"
        "    for e in ledger.events(sys.argv[2], after_seq=cursor):\n"
        "        cursor = e['seq']; print(e['type'], flush=True)\n"
        "    time.sleep(0.01)\n"
    )
    worker = _spawn_worker(db, root, "worker-a", lease=5.0)
    follower = subprocess.Popen(
        [sys.executable, "-c", follower_code, str(db), job_id],
        env=_env(),
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        _wait(lambda: len(_checkpoints(db, job_id)) >= 3, "progress")
        assert follower.poll() is None, "follower was not connected"
        seen_before_kill = len(_checkpoints(db, job_id))
    finally:
        follower.kill()
        follower.wait()
    assert worker.poll() is None, "worker stopped with the client"
    _finish(worker)
    with JobLedger(db) as ledger:
        assert ledger.job(job_id)["state"] == JOB_SUCCEEDED
    assert len(_checkpoints(db, job_id)) > seen_before_kill
    # One worker did all of it: the disconnection caused no re-claim.
    with JobLedger(db) as ledger:
        assert _types(ledger, job_id).count("OP_CLAIMED") == 1


# -- 03 --------------------------------------------------------------------


def test_03_execution_survives_worker_interruption(tmp_path, paths):
    """SIGKILL the worker mid-retrieval; a second worker finishes the job."""

    db, root = paths
    source = _source(tmp_path)
    with JobLedger(db) as ledger:
        job_id = ledger.submit(
            kind="acquisition",
            idempotency_key="int-1",
            operations=[
                _copy_op(source, delay=0.03),
                OperationSpec(name="bind", kind="noop", depends_on=("retrieve",)),
            ],
        )
    _kill_mid_copy(db, root, job_id)
    with JobLedger(db) as ledger:
        assert ledger.job(job_id)["operations"][0]["state"] == "RUNNING"

    _finish(_spawn_worker(db, root, "worker-b"))
    with JobLedger(db) as ledger:
        job = ledger.job(job_id)
        types = _types(ledger, job_id)
    assert job["state"] == JOB_SUCCEEDED
    assert [op["state"] for op in job["operations"]] == [OP_SUCCEEDED, OP_SUCCEEDED]
    assert "LEASE_EXPIRED" in types
    artifact = Path(job["operations"][0]["result"]["path"])
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == source[1]
    assert not artifact.with_name(artifact.name + ".part").exists()


# -- 04 --------------------------------------------------------------------


def test_04_checkpoints_survive_process_restart(tmp_path, paths):
    """After the kill, a fresh process reads back the last checkpoint written."""

    db, root = paths
    source = _source(tmp_path)
    with JobLedger(db) as ledger:
        job_id = ledger.submit(
            kind="acquisition",
            idempotency_key="ckpt-1",
            operations=[_copy_op(source, delay=0.03)],
        )
    last = _kill_mid_copy(db, root, job_id)

    reader = (
        "import sys, json\n"
        "from spiderweb.geo_sar.jobs import JobLedger\n"
        "with JobLedger(sys.argv[1]) as ledger:\n"
        "    op = ledger.job(sys.argv[2])['operations'][0]\n"
        "    print(json.dumps([op['checkpoint_seq'], op['checkpoint']]))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", reader, str(db), job_id],
        env=_env(),
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=True,
    )
    seq, checkpoint = json.loads(out.stdout)
    assert seq == last["payload"]["checkpoint_seq"]
    assert checkpoint == last["payload"]["data"]
    # The bytes the checkpoint describes are on disk and hash as recorded.
    part = root / _copy_op(source, delay=0).params["dest"]
    part = part.with_name(part.name + ".part")
    prefix = part.read_bytes()[: checkpoint["offset"]]
    assert hashlib.sha256(prefix).hexdigest() == checkpoint["prefix_sha256"]


# -- 05 --------------------------------------------------------------------


def test_05_recovery_does_not_duplicate_mutations(tmp_path, paths):
    """One artifact, one effect; unsafe interrupted changes are never replayed."""

    db, root = paths
    source = _source(tmp_path)
    with JobLedger(db) as ledger:
        job_id = ledger.submit(
            kind="acquisition",
            idempotency_key="dup-1",
            operations=[_copy_op(source, delay=0.03)],
        )
    _kill_mid_copy(db, root, job_id)
    _finish(_spawn_worker(db, root, "worker-b"))

    # A second job needing the same bytes reuses the artifact: nothing written.
    with JobLedger(db) as ledger:
        again = ledger.submit(
            kind="acquisition",
            idempotency_key="dup-2",
            operations=[_copy_op(source, delay=0)],
        )
    _finish(_spawn_worker(db, root, "worker-c"))

    with JobLedger(db) as ledger:
        first, second = ledger.job(job_id), ledger.job(again)
        assert _types(ledger, job_id).count("EFFECT_RECORDED") == 1
        assert _types(ledger, again).count("EFFECT_RECORDED") == 0
        assert _types(ledger, again).count("EFFECT_REUSED") == 1
    assert second["operations"][0]["result"]["reused"] is True
    assert second["operations"][0]["result"]["bytes_written_this_attempt"] == 0
    connection = sqlite3.connect(db)
    assert connection.execute("SELECT COUNT(*) FROM effects").fetchone()[0] == 1
    connection.close()
    assert len([p for p in root.rglob("*") if p.is_file()]) == 1
    assert (
        first["operations"][0]["result"]["path"]
        == second["operations"][0]["result"]["path"]
    )

    # Submitting the same job again creates nothing.
    with JobLedger(db) as ledger:
        assert (
            ledger.submit(
                kind="acquisition",
                idempotency_key="dup-1",
                operations=[_copy_op(source, delay=0.03)],
            )
            == job_id
        )
        with pytest.raises(IdempotencyConflict):
            ledger.submit(
                kind="acquisition",
                idempotency_key="dup-1",
                operations=[_copy_op(source, delay=0.5)],
            )

    # A mutating step not declared resumable is stopped, not replayed.
    with JobLedger(db) as ledger:
        unsafe = ledger.submit(
            kind="registry_write",
            idempotency_key="unsafe-1",
            operations=[
                OperationSpec(
                    name="write", kind="sleep", params={"seconds": 30}, mutating=True
                ),
                OperationSpec(name="after", kind="noop", depends_on=("write",)),
            ],
        )
    worker = _spawn_worker(db, root, "worker-d", lease=0.5)
    with JobLedger(db) as ledger:
        _wait(lambda: "OP_CLAIMED" in _types(ledger, unsafe), "claim")
    os.killpg(worker.pid, signal.SIGKILL)
    worker.wait()
    time.sleep(0.7)
    _finish(_spawn_worker(db, root, "worker-e", lease=0.5))
    with JobLedger(db) as ledger:
        job = ledger.job(unsafe)
        assert job["state"] == JOB_NEEDS_RECONCILIATION
        assert job["operations"][0]["state"] == OP_NEEDS_RECONCILIATION
        assert job["operations"][0]["attempts"] == 1
        assert job["operations"][1]["state"] == OP_PENDING
        assert _types(ledger, unsafe).count("OP_CLAIMED") == 1


# -- 06 --------------------------------------------------------------------


def test_06_authorization_boundaries_remain_enforced(tmp_path, paths):
    """No grant, wrong grant, too small a grant, and a lost lease all refuse."""

    db, root = paths
    source = _source(tmp_path)
    size = source[2]
    with JobLedger(db) as ledger:
        none = ledger.submit(
            kind="acquisition",
            idempotency_key="auth-none",
            operations=[
                _copy_op(source, delay=0, required_level=LEVEL_PRODUCT),
                OperationSpec(name="bind", kind="noop", depends_on=("retrieve",)),
            ],
        )
        wrong = ledger.submit(
            kind="acquisition",
            idempotency_key="auth-wrong",
            operations=[_copy_op(source, delay=0, required_level=LEVEL_PRODUCT)],
            grant={
                "level": "METADATA_DISCOVERY",
                "granted_by": "owner",
                "max_requests": 150,
            },
        )
        small = ledger.submit(
            kind="acquisition",
            idempotency_key="auth-small",
            operations=[_copy_op(source, delay=0, required_level=LEVEL_PRODUCT)],
            grant={
                "level": LEVEL_PRODUCT,
                "granted_by": "owner",
                "max_requests": 1,
                "max_bytes": size - 1,
            },
        )
        with pytest.raises(InvalidJob):
            ledger.submit(
                kind="acquisition",
                idempotency_key="auth-anon",
                operations=[_copy_op(source, delay=0)],
                grant={"level": LEVEL_PRODUCT, "max_requests": 1, "max_bytes": size},
            )
    # Interrupt a worker, then run another: recovery must not open the gate.
    worker = _spawn_worker(db, root, "worker-a")
    time.sleep(0.3)
    os.killpg(worker.pid, signal.SIGKILL)
    worker.wait()
    _finish(_spawn_worker(db, root, "worker-b"))

    with JobLedger(db) as ledger:
        for job_id in (none, wrong, small):
            job = ledger.job(job_id)
            assert job["state"] == JOB_BLOCKED
            assert job["operations"][0]["state"] == OP_BLOCKED
            assert job["operations"][0]["attempts"] == 0
            types = _types(ledger, job_id)
            assert "AUTHORIZATION_DENIED" in types
            assert "RETRIEVAL_STARTED" not in types and "OP_CLAIMED" not in types
        assert ledger.job(none)["operations"][1]["state"] == OP_BLOCKED
        assert "byte ceiling" in ledger.job(small)["operations"][0]["error"]
    assert not root.exists() or not [p for p in root.rglob("*") if p.is_file()]

    # A sufficient grant runs; the stored grant cannot be altered through the API.
    with JobLedger(db) as ledger:
        ok = ledger.submit(
            kind="acquisition",
            idempotency_key="auth-ok",
            operations=[_copy_op(source, delay=0, required_level=LEVEL_PRODUCT)],
            grant={
                "level": LEVEL_PRODUCT,
                "granted_by": "owner",
                "max_requests": 1,
                "max_bytes": size,
            },
        )
        assert not [
            n for n in dir(ledger) if "grant" in n.lower() and not n.startswith("_")
        ]
    _finish(_spawn_worker(db, root, "worker-c"))
    with JobLedger(db) as ledger:
        assert ledger.job(ok)["state"] == JOB_SUCCEEDED

    # Fencing: a worker whose lease was taken over can no longer write.
    with JobLedger(db) as ledger:
        ledger.submit(
            kind="probe",
            idempotency_key="fence-1",
            operations=[OperationSpec(name="probe", kind="noop")],
        )
        stale = ledger.claim("worker-old", lease_seconds=0.05)
        assert stale is not None
        time.sleep(0.1)
        fresh = ledger.claim("worker-new", lease_seconds=30)
        assert fresh is not None and fresh.generation == stale.generation + 1
        for write in (
            lambda: ledger.complete(stale, {"late": True}),
            lambda: ledger.checkpoint(stale, {"x": 1}, lease_seconds=30),
            lambda: ledger.record_effect(stale, "late-effect", {"x": 1}),
            lambda: ledger.fail(stale, "late"),
        ):
            with pytest.raises(StaleLease):
                write()
        assert ledger.lookup_effect("late-effect") is None
        ledger.complete(fresh, {"ok": True})


# -- 07 --------------------------------------------------------------------


def test_07_evidence_history_remains_intact(tmp_path, paths):
    """History cannot be rewritten, and survives the kill without loss."""

    db, root = paths
    source = _source(tmp_path)
    with JobLedger(db) as ledger:
        job_id = ledger.submit(
            kind="acquisition",
            idempotency_key="hist-1",
            operations=[_copy_op(source, delay=0.03)],
        )
    _kill_mid_copy(db, root, job_id)
    with JobLedger(db) as ledger:
        before = ledger.events(job_id)
    _finish(_spawn_worker(db, root, "worker-b"))
    with JobLedger(db) as ledger:
        after = ledger.events(job_id)

    assert after[: len(before)] == before, "earlier history changed"
    seqs = [e["seq"] for e in after]
    assert seqs == sorted(set(seqs))
    # Every checkpoint ever taken is still readable, including superseded ones.
    numbers = [
        e["payload"]["checkpoint_seq"] for e in after if e["type"] == "CHECKPOINT"
    ]
    assert numbers == list(range(1, len(numbers) + 1))
    assert {e["payload"]["generation"] for e in after if e["type"] == "CHECKPOINT"} == {
        1,
        2,
    }

    connection = sqlite3.connect(db)
    for statement in (
        "UPDATE events SET type='REWRITTEN'",
        "DELETE FROM events",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(statement)
    connection.close()
    with JobLedger(db) as ledger:
        assert ledger.events(job_id) == after


# -- 08 --------------------------------------------------------------------


def test_08_resume_starts_from_latest_verified_checkpoint(tmp_path, paths):
    """Resume continues at the last checkpoint; an unverifiable one is rejected."""

    db, root = paths
    source = _source(tmp_path)
    total = source[2]
    with JobLedger(db) as ledger:
        job_id = ledger.submit(
            kind="acquisition",
            idempotency_key="resume-1",
            operations=[_copy_op(source, delay=0.03)],
        )
    last = _kill_mid_copy(db, root, job_id)
    offset = last["payload"]["data"]["offset"]
    assert 0 < offset < total
    _finish(_spawn_worker(db, root, "worker-b"))
    with JobLedger(db) as ledger:
        job = ledger.job(job_id)
        starts = [e for e in ledger.events(job_id) if e["type"] == "RETRIEVAL_STARTED"]
    assert [s["payload"]["start_offset"] for s in starts] == [0, offset]
    assert (
        starts[1]["payload"]["from_checkpoint_seq"] == last["payload"]["checkpoint_seq"]
    )
    assert (
        job["operations"][0]["result"]["bytes_written_this_attempt"] == total - offset
    )
    assert job["state"] == JOB_SUCCEEDED

    # Same interruption, but the partial file is damaged before the restart.
    db2, root2 = tmp_path / "ledger2" / "jobs.sqlite", tmp_path / "artifacts2"
    with JobLedger(db2) as ledger:
        job2 = ledger.submit(
            kind="acquisition",
            idempotency_key="resume-2",
            operations=[_copy_op(source, delay=0.03)],
        )
    _kill_mid_copy(db2, root2, job2)
    part = root2 / _copy_op(source, delay=0).params["dest"]
    part = part.with_name(part.name + ".part")
    damaged = bytearray(part.read_bytes())
    damaged[10] ^= 0xFF
    part.write_bytes(bytes(damaged))
    _finish(_spawn_worker(db2, root2, "worker-b"))
    with JobLedger(db2) as ledger:
        result = ledger.job(job2)
        types = _types(ledger, job2)
        starts = [e for e in ledger.events(job2) if e["type"] == "RETRIEVAL_STARTED"]
    assert "CHECKPOINT_REJECTED" in types
    assert starts[-1]["payload"]["start_offset"] == 0
    assert result["state"] == JOB_SUCCEEDED
    final = Path(result["operations"][0]["result"]["path"])
    assert hashlib.sha256(final.read_bytes()).hexdigest() == source[1]


# -- 09 --------------------------------------------------------------------


def test_09_terminal_failures_are_accurately_reported(tmp_path, paths):
    """Bounded retries, then FAILED with the cause; integrity failure is final."""

    db, root = paths
    path, sha, size = _source(tmp_path)
    with JobLedger(db) as ledger:
        failing = ledger.submit(
            kind="acquisition",
            idempotency_key="fail-1",
            operations=[
                OperationSpec(
                    name="retrieve",
                    kind="always_fail",
                    params={"message": "provider returned 503"},
                    max_attempts=3,
                ),
                OperationSpec(name="verify", kind="noop", depends_on=("retrieve",)),
                OperationSpec(name="bind", kind="noop", depends_on=("verify",)),
            ],
        )
        corrupt = ledger.submit(
            kind="acquisition",
            idempotency_key="fail-2",
            operations=[
                _copy_op((path, "0" * 64, size), delay=0),
            ],
        )
        unknown = ledger.submit(
            kind="acquisition",
            idempotency_key="fail-3",
            operations=[OperationSpec(name="x", kind="not_a_handler")],
        )
    _finish(_spawn_worker(db, root, "worker-a"))

    with JobLedger(db) as ledger:
        job = ledger.job(failing)
        assert job["state"] == JOB_FAILED
        retrieve, verify, bind = job["operations"]
        assert (retrieve["state"], retrieve["attempts"]) == (OP_FAILED, 3)
        assert retrieve["error"] == "provider returned 503"
        assert verify["state"] == bind["state"] == OP_BLOCKED
        assert "retrieve did not succeed" in verify["error"]
        types = _types(ledger, failing)
        assert types.count("OP_ATTEMPT_FAILED") == 2 and types.count("OP_FAILED") == 1
        assert "OP_SUCCEEDED" not in types

        bad = ledger.job(corrupt)
        assert bad["state"] == JOB_FAILED
        assert bad["operations"][0]["attempts"] == 1, "integrity failure was retried"
        assert "integrity check failed" in bad["operations"][0]["error"]
        assert ledger.lookup_effect(f"artifact:sha256:{'0' * 64}") is None

        assert ledger.job(unknown)["state"] == JOB_FAILED
        assert "no handler" in ledger.job(unknown)["operations"][0]["error"]
    assert not [p for p in root.rglob("*") if p.is_file()], "a failed artifact was kept"


# -- 10 --------------------------------------------------------------------


def test_10_later_session_reconnects_to_original_job(tmp_path, paths):
    """A new process finds the job by its key and reads only what it missed."""

    db, root = paths
    source = _source(tmp_path)
    with JobLedger(db) as ledger:
        job_id = ledger.submit(
            kind="acquisition",
            idempotency_key="segment:PRG2:L1:R010:C0020|USGS_3DEP_1M|D24",
            operations=[_copy_op(source, delay=0.03)],
        )
    _kill_mid_copy(db, root, job_id)
    with JobLedger(db) as ledger:
        cursor = ledger.events(job_id)[-1]["seq"]
    _finish(_spawn_worker(db, root, "worker-b"))

    session = (
        "import sys, json\n"
        "from spiderweb.geo_sar.jobs import JobLedger\n"
        "with JobLedger(sys.argv[1]) as ledger:\n"
        "    job_id = ledger.find_job(sys.argv[2])\n"
        "    missed = ledger.events(job_id, after_seq=int(sys.argv[3]))\n"
        "    print(json.dumps({'job_id': job_id, 'state': ledger.job(job_id)['state'],\n"
        "        'first': missed[0]['seq'], 'types': [e['type'] for e in missed]}))\n"
    )
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            session,
            str(db),
            "segment:PRG2:L1:R010:C0020|USGS_3DEP_1M|D24",
            str(cursor),
        ],
        env=_env(),
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=True,
    )
    seen = json.loads(out.stdout)
    assert seen["job_id"] == job_id
    assert seen["state"] == JOB_SUCCEEDED
    assert seen["first"] == cursor + 1
    assert seen["types"][0] == "LEASE_EXPIRED"
    assert seen["types"][-1] == "JOB_STATE" and "OP_SUCCEEDED" in seen["types"]
    assert "JOB_SUBMITTED" not in seen["types"]


# -- ledger rules not tied to one numbered test ----------------------------


def test_dependency_cycles_and_unknown_dependencies_are_refused(paths):
    db, _ = paths
    with JobLedger(db) as ledger:
        with pytest.raises(InvalidJob, match="cycle"):
            ledger.submit(
                kind="k",
                idempotency_key="cycle",
                operations=[
                    OperationSpec(name="a", kind="noop", depends_on=("b",)),
                    OperationSpec(name="b", kind="noop", depends_on=("a",)),
                ],
            )
        with pytest.raises(InvalidJob, match="unknown"):
            ledger.submit(
                kind="k",
                idempotency_key="missing",
                operations=[OperationSpec(name="a", kind="noop", depends_on=("z",))],
            )
        assert ledger.find_job("cycle") is None


def test_reconciliation_needs_a_named_decision(paths):
    db, _ = paths
    with JobLedger(db) as ledger:
        job_id = ledger.submit(
            kind="k",
            idempotency_key="rec",
            operations=[OperationSpec(name="write", kind="noop", mutating=True)],
        )
        claim = ledger.claim("w", lease_seconds=0.01)
        assert claim is not None
        time.sleep(0.05)
        assert ledger.reconcile_expired() == [claim.op_id]
        assert ledger.claim("w2", lease_seconds=10) is None
        with pytest.raises(ValueError):
            ledger.resolve_reconciliation(
                claim.op_id, outcome="RETRY", resolved_by="", note=""
            )
        ledger.resolve_reconciliation(
            claim.op_id,
            outcome="RETRY",
            resolved_by="owner",
            note="registry file unchanged; checked by hash",
        )
        retry = ledger.claim("w2", lease_seconds=10)
        assert retry is not None and retry.attempt == 2
        ledger.complete(retry)
        assert ledger.job(job_id)["state"] == JOB_SUCCEEDED
