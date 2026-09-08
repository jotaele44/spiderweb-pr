"""Exercise backend child commands without downloading models or production data."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("aiosqlite")
pytest.importorskip("sse_starlette")
from server.backend import main as backend


@pytest.mark.parametrize("phase", [None, 2, 3, 4])
def test_pipeline_uses_active_interpreter(monkeypatch, phase):
    popen = Mock()
    monkeypatch.setattr(backend.subprocess, "Popen", popen)
    monkeypatch.setattr(backend, "_jobs", {})
    result = asyncio.run(backend.pipeline_run(backend.PipelineRunRequest(phase=phase)))
    cmd = popen.call_args.args[0]
    assert cmd == [sys.executable, "-u", str(backend.ROOT / "run_all.py")] + (
        [] if phase is None else ["--phase", str(phase)]
    )
    assert backend._jobs[result["job_id"]] is popen.return_value


def test_index_invokes_existing_module_in_build_mode(monkeypatch):
    popen = Mock()
    monkeypatch.setattr(backend.subprocess, "Popen", popen)
    monkeypatch.setattr(backend, "_jobs", {})
    asyncio.run(backend.rag_index())
    assert popen.call_args.args[0] == [
        sys.executable,
        "-u",
        "-m",
        "llm.rag_pipeline",
        "--build",
    ]
    assert (Path(popen.call_args.kwargs["cwd"]) / "llm/rag_pipeline.py").is_file()


def test_pipeline_done_waits_for_real_exit_code():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import os,time; os.close(1); time.sleep(.1); exit(7)"],
        stdout=subprocess.PIPE,
        text=True,
    )

    async def collect():
        return [event async for event in backend._stream_stdout(proc)]

    try:
        events = asyncio.run(collect())
        assert json.loads(events[-1]["data"]) == {"returncode": 7}
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        proc.stdout.close()


def test_rag_drains_stderr_and_reports_failure(monkeypatch, tmp_path):
    (tmp_path / "query_llm.py").write_text(
        "import sys\nsys.stderr.write('e' * 200000 + '\\n')\n"
        "print('diagnostic')\nsys.exit(9)\n"
    )
    monkeypatch.setattr(backend, "ROOT", tmp_path)
    real_popen = subprocess.Popen
    children = []

    def spawn(cmd, **kwargs):
        assert cmd[:2] == [sys.executable, "-u"]
        assert kwargs["stderr"] == subprocess.STDOUT
        proc = real_popen(cmd, **kwargs)
        children.append(proc)
        return proc

    monkeypatch.setattr(backend.subprocess, "Popen", spawn)

    async def collect():
        return [event async for event in backend._stream_rag("test", 5, False)]

    try:
        events = asyncio.run(collect())
        assert any(event["data"] == "diagnostic" for event in events)
        assert json.loads(events[-1]["data"]) == {"returncode": 9}
    finally:
        for proc in children:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()
