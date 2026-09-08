"""Real subprocess regressions for diagnostic job ownership and replay."""

import asyncio
import json
import os
import sys
import time

import pytest

from server.backend.jobs import JobCapacityError, JobRegistry


@pytest.fixture
def registry():
    value = JobRegistry()
    try:
        yield value
    finally:
        value.close()


def command(source):
    return [sys.executable, "-u", "-c", source]


def wait_done(job):
    assert job.done.wait(15), "child/capture did not finish"


async def collect(job):
    return [event async for event in job.events()]


def test_verbose_job_finishes_without_a_viewer_and_replays_to_two_viewers(
    registry, tmp_path
):
    job = registry.submit(
        "verbose", command("import sys; sys.stdout.write('x' * 8388608)"), cwd=tmp_path
    )
    wait_done(job)
    assert job.status() == {"status": "done", "returncode": 0}

    async def viewers():
        return await asyncio.gather(collect(job), collect(job))

    first, second = asyncio.run(viewers())
    assert first == second
    assert sum(len(event["data"]) for event in first if "event" not in event) == 8388608
    assert json.loads(first[-1]["data"]) == {"returncode": 0}


def test_live_viewers_receive_identical_complete_history(registry, tmp_path):
    job = registry.submit(
        "live",
        command(
            "import time\nfor i in range(20):\n print(i, flush=True)\n time.sleep(.02)"
        ),
        cwd=tmp_path,
    )

    async def viewers():
        return await asyncio.gather(collect(job), collect(job))

    first, second = asyncio.run(viewers())
    assert first == second
    assert [e["data"] for e in first[:-1]] == [str(i) for i in range(20)]


def test_disconnecting_a_viewer_does_not_stop_pipeline(registry, tmp_path):
    job = registry.submit(
        "disconnect",
        command(
            "import time; print('first',flush=True); time.sleep(.2); print('last')"
        ),
        cwd=tmp_path,
    )

    async def disconnect():
        stream = job.events()
        assert (await anext(stream))["data"] == "first"
        await stream.aclose()

    asyncio.run(disconnect())
    wait_done(job)
    assert job.status()["status"] == "done"
    assert [e["data"] for e in asyncio.run(collect(job))[:-1]] == ["first", "last"]


def test_output_limit_is_bounded_and_reported_as_failure(tmp_path):
    registry = JobRegistry(max_output_bytes=4096)
    try:
        job = registry.submit(
            "limit",
            command("import sys; sys.stdout.write('x' * 1000000)"),
            cwd=tmp_path,
        )
        wait_done(job)
        assert job.output_bytes == 4096
        assert job.status()["status"] == "error"
        assert job.status()["error"] == "output_limit_exceeded"
        result = json.loads(asyncio.run(collect(job))[-1]["data"])
        assert result["returncode"] != 0
        assert result["error"] == "output_limit_exceeded"
    finally:
        registry.close()


def test_capture_preserves_spacing_and_handles_split_unicode(registry, tmp_path):
    payload = "  " + "é" * 40000 + "  "
    job = registry.submit("unicode", command(f"print({payload!r})"), cwd=tmp_path)
    wait_done(job)
    events = asyncio.run(collect(job))
    assert "".join(e["data"] for e in events[:-1]) == payload


def test_waits_for_exit_after_stdout_closes(registry, tmp_path):
    job = registry.submit(
        "early-close",
        command("import os,time; os.close(1); os.close(2); time.sleep(.2); exit(7)"),
        cwd=tmp_path,
    )
    wait_done(job)
    assert json.loads(asyncio.run(collect(job))[-1]["data"])["returncode"] == 7


def test_capacity_rejection_precedes_child_launch_and_completed_jobs_are_evicted(
    tmp_path,
):
    registry = JobRegistry(max_running=1, max_retained=1)
    try:
        first = registry.submit(
            "first", command("import time; time.sleep(60)"), cwd=tmp_path
        )
        with pytest.raises(JobCapacityError):
            registry.submit(
                "second", command("raise AssertionError('must not run')"), cwd=tmp_path
            )
        assert first.stop()
        second = registry.submit("second", command("print('ok')"), cwd=tmp_path)
        wait_done(second)
        assert registry.get("first") is None
        assert first.closed
    finally:
        registry.close()


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group regression")
def test_cancellation_kills_descendants_holding_stdout(registry, tmp_path):
    job = registry.submit(
        "descendant",
        command(
            "import subprocess,sys,time\n"
            "subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n"
            "print('ready',flush=True)\ntime.sleep(60)"
        ),
        cwd=tmp_path,
    )
    deadline = time.monotonic() + 10
    while job.output_bytes == 0 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert job.output_bytes > 0
    assert job.stop()
    assert job.done.is_set()
    assert job.proc.poll() is not None
    assert job.status()["status"] == "terminated"


def test_shutdown_reaps_running_children(tmp_path):
    registry = JobRegistry()
    job = registry.submit(
        "shutdown", command("import time; time.sleep(60)"), cwd=tmp_path
    )
    registry.close()
    assert job.done.is_set()
    assert job.proc.poll() is not None
    assert job.closed


def test_failed_launch_does_not_consume_registry_capacity(tmp_path):
    registry = JobRegistry(max_running=1, max_retained=1)
    try:
        with pytest.raises(FileNotFoundError):
            registry.submit(
                "missing", [str(tmp_path / "missing-executable")], cwd=tmp_path
            )
        job = registry.submit("valid", command("pass"), cwd=tmp_path)
        wait_done(job)
        assert job.status()["status"] == "done"
    finally:
        registry.close()


def test_capacity_does_not_evict_an_active_reader(tmp_path):
    registry = JobRegistry(max_running=1, max_retained=1)
    try:
        job = registry.submit(
            "first", command("print('first'); print('second')"), cwd=tmp_path
        )
        wait_done(job)

        async def reading():
            stream = job.events()
            await anext(stream)
            with pytest.raises(JobCapacityError):
                registry.submit("next", command("pass"), cwd=tmp_path)
            await stream.aclose()

        asyncio.run(reading())
    finally:
        registry.close()


def test_api_capacity_is_reported_before_stream_headers(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from server.backend import main as backend

    registry = JobRegistry(max_running=1, max_retained=1)
    monkeypatch.setattr(backend, "_jobs", registry)
    registry.submit("occupied", command("import time; time.sleep(60)"), cwd=tmp_path)
    with TestClient(backend.app) as client:
        for path, payload in [
            ("/pipeline/run", {}),
            ("/rag/index", {}),
            ("/rag/query", {"query": "test"}),
        ]:
            response = client.post(path, json=payload)
            assert response.status_code == 429
            assert "maximum running" in response.json()["detail"]


def test_api_late_replay_resume_and_idempotent_stop(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from server.backend import main as backend

    registry = JobRegistry()
    monkeypatch.setattr(backend, "_jobs", registry)
    job = registry.submit(
        "finished", command("print('one'); print('two')"), cwd=tmp_path
    )
    wait_done(job)
    with TestClient(backend.app) as client:
        assert client.get("/pipeline/status/finished").json()["status"] == "done"
        assert client.get("/pipeline/jobs").json() == [
            {"job_id": "finished", "status": "done", "returncode": 0, "output_bytes": 8}
        ]
        response = client.get(
            "/pipeline/events/finished", headers={"Last-Event-ID": "4"}
        )
        assert response.status_code == 200
        assert "data: one" not in response.text
        assert "data: two" in response.text
        assert "event: done" in response.text
        for cursor in ["-1", "99999", "not-a-number"]:
            assert (
                client.get(
                    "/pipeline/events/finished", headers={"Last-Event-ID": cursor}
                ).status_code
                == 400
            )
        for _ in range(2):
            response = client.delete("/pipeline/finished")
            assert response.status_code == 200
            assert response.json()["status"] == "done"


def test_invalid_output_bytes_are_retained_and_stream_is_decodable(registry, tmp_path):
    job = registry.submit(
        "binary", command("import os; os.write(1,b'\\xff  \\n')"), cwd=tmp_path
    )
    wait_done(job)
    assert job._readline(0) == b"\xff  \n"
    events = asyncio.run(collect(job))
    assert events[0]["data"] == "\ufffd  "


def test_invalid_prefix_does_not_corrupt_valid_unicode_at_chunk_boundary(
    registry, tmp_path
):
    job = registry.submit(
        "mixed",
        command("import os; os.write(1, b'\\xff' + ('é' * 40000).encode() + b'\\n')"),
        cwd=tmp_path,
    )
    wait_done(job)
    events = asyncio.run(collect(job))
    assert "".join(event["data"] for event in events[:-1]) == "\ufffd" + "é" * 40000


@pytest.mark.skipif(os.name != "posix", reason="POSIX signal handler regression")
@pytest.mark.parametrize("process_group", [True, False])
def test_cancellation_escalates_when_child_ignores_termination(
    registry, tmp_path, process_group
):
    job = registry.submit(
        "ignore-term",
        command(
            "import signal,time; "
            "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
            "print('ready',flush=True); time.sleep(60)"
        ),
        cwd=tmp_path,
    )
    job.owns_process_group = process_group
    deadline = time.monotonic() + 10
    while job.output_bytes == 0 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert job.output_bytes > 0
    assert job.stop(timeout=0.2)
    assert job.proc.returncode != 0


def test_duplicate_job_id_cannot_replace_a_live_child(registry, tmp_path):
    job = registry.submit(
        "same-id", command("import time; time.sleep(60)"), cwd=tmp_path
    )
    with pytest.raises(ValueError, match="duplicate"):
        registry.submit("same-id", command("pass"), cwd=tmp_path)
    assert registry.get("same-id") is job


def test_expired_output_is_an_explicit_stream_error(tmp_path):
    registry = JobRegistry(max_running=1, max_retained=1)
    try:
        old = registry.submit("old", command("print('old')"), cwd=tmp_path)
        wait_done(old)
        registry.submit("new", command("pass"), cwd=tmp_path)
        assert asyncio.run(collect(old)) == [
            {"event": "error", "data": "job output was evicted"}
        ]
    finally:
        registry.close()


def test_rag_viewer_disconnect_cleans_up_its_owned_job(monkeypatch, tmp_path):
    from server.backend import main as backend

    registry = JobRegistry()
    monkeypatch.setattr(backend, "_jobs", registry)
    job = registry.submit(
        "rag",
        command("import time; print('ready',flush=True); time.sleep(60)"),
        cwd=tmp_path,
    )

    async def disconnect():
        events = backend._rag_events("rag", job)
        assert (await anext(events))["data"] == "ready"
        await events.aclose()

    asyncio.run(disconnect())
    assert job.done.is_set()
    assert registry.get("rag") is None
    assert job.closed


def test_capture_storage_failure_is_not_a_success(monkeypatch, tmp_path):
    from server.backend import jobs

    create_file = jobs.tempfile.TemporaryFile

    class BrokenOutput:
        def __init__(self):
            self.file = create_file(mode="w+b")

        def __getattr__(self, name):
            return getattr(self.file, name)

        def write(self, data):
            raise OSError("fixture disk full")

    monkeypatch.setattr(jobs.tempfile, "TemporaryFile", lambda **_: BrokenOutput())
    registry = JobRegistry()
    try:
        job = registry.submit("disk-failure", command("print('output')"), cwd=tmp_path)
        wait_done(job)
        assert job.status()["status"] == "error"
        assert job.status()["error"] == "output_capture_failed: OSError"
        assert job.status()["returncode"] != 0
        assert job.status()["process_returncode"] == job.proc.returncode
    finally:
        registry.close()


def test_capture_thread_start_failure_reaps_child(monkeypatch, tmp_path):
    from server.backend import jobs

    children = []
    spawn = jobs.subprocess.Popen

    def recorded_spawn(*args, **kwargs):
        child = spawn(*args, **kwargs)
        children.append(child)
        return child

    def failed_start(_):
        raise RuntimeError("fixture cannot start thread")

    monkeypatch.setattr(jobs.subprocess, "Popen", recorded_spawn)
    monkeypatch.setattr(jobs.threading.Thread, "start", failed_start)
    registry = JobRegistry()
    with pytest.raises(RuntimeError, match="cannot start thread"):
        registry.submit(
            "thread-failure", command("import time; time.sleep(60)"), cwd=tmp_path
        )
    assert registry.snapshot() == []
    assert len(children) == 1
    assert children[0].poll() is not None
    assert children[0].stdout.closed
