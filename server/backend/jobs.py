"""Bounded diagnostic jobs with viewer-independent, byte-preserving capture.

The registry is process-local. Output is retained until completed-job eviction
or orderly shutdown; this is not a durable queue or automatic restart facility.
"""

from __future__ import annotations

import asyncio
import codecs
import json
import os
import signal
import subprocess
import tempfile
import threading
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from pathlib import Path


class JobCapacityError(RuntimeError):
    """No active or retained job slot is available."""


class ManagedJob:
    def __init__(
        self,
        proc: subprocess.Popen,
        *,
        max_output_bytes: int,
        owns_process_group: bool = False,
    ) -> None:
        self.proc = proc
        self.owns_process_group = owns_process_group
        self.max_output_bytes = max_output_bytes
        self.output_bytes = 0
        self.returncode: int | None = None
        self.error: str | None = None
        self.cancelled = False
        self.readers = 0
        self.closed = False
        self.done = threading.Event()
        self._lock = threading.RLock()
        self._process_lock = threading.Lock()
        self._process_finished = False
        self._output = tempfile.TemporaryFile(mode="w+b")
        self._thread = threading.Thread(target=self._capture, daemon=True)
        try:
            self._thread.start()
        except Exception:
            self._output.close()
            raise

    def _signal(self, *, force: bool = False) -> None:
        with self._process_lock:
            if self._process_finished:
                return
            try:
                if self.owns_process_group and os.name == "posix":
                    # Every registry child owns a new session. Kill its group,
                    # including descendants that may still hold the pipe open.
                    os.killpg(
                        self.proc.pid, signal.SIGKILL if force else signal.SIGTERM
                    )
                elif force:
                    self.proc.kill()
                else:
                    self.proc.terminate()
            except ProcessLookupError:
                pass

    def _capture(self) -> None:
        try:
            assert self.proc.stdout is not None
            while chunk := os.read(self.proc.stdout.fileno(), 65536):
                with self._lock:
                    remaining = self.max_output_bytes - self.output_bytes
                    retained = chunk[:remaining]
                    self._output.seek(0, 2)
                    self._output.write(retained)
                    self._output.flush()
                    self.output_bytes += len(retained)
                    if len(chunk) > remaining:
                        self.error = "output_limit_exceeded"
                if self.error:
                    self._signal(force=True)
                    break
        except Exception as exc:
            with self._lock:
                self.error = f"output_capture_failed: {type(exc).__name__}"
            self._signal(force=True)
        finally:
            if self.proc.stdout is not None:
                try:
                    self.proc.stdout.close()
                except OSError as exc:
                    self.error = (
                        self.error or f"pipe_close_failed: {type(exc).__name__}"
                    )
                    self._signal(force=True)
            # Poll under the same lock as signalling to avoid signalling a
            # reaped/reused PID. Never hold that lock while waiting for exit.
            while True:
                with self._process_lock:
                    rc = self.proc.poll()
                    if rc is not None:
                        self._process_finished = True
                        self.returncode = rc
                        break
                time.sleep(0.02)
            self.done.set()

    def status(self) -> dict:
        if not self.done.is_set():
            return {"status": "running"}
        result = {
            "status": (
                "terminated"
                if self.cancelled
                else ("done" if self.returncode == 0 and not self.error else "error")
            ),
            "returncode": (
                self.returncode
                if not (self.error or self.cancelled)
                else (self.returncode or 1)
            ),
        }
        if self.error or self.cancelled:
            result["process_returncode"] = self.returncode
        if self.error:
            result["error"] = self.error
        return result

    def stop(self, timeout: float = 2.0) -> bool:
        if self.done.is_set():
            return True
        self.cancelled = True
        self._signal()
        if not self.done.wait(timeout):
            self._signal(force=True)
        return self.done.wait(timeout)

    def close(self) -> None:
        if not self.stop():
            raise RuntimeError("child did not stop; output capture remains owned")
        with self._lock:
            self.closed = True
            self._output.close()

    def close_if_idle(self) -> bool:
        with self._lock:
            if not self.done.is_set() or self.readers:
                return False
            self.closed = True
            self._output.close()
            return True

    def _readline(self, offset: int) -> bytes | None:
        with self._lock:
            if self.closed:
                raise RuntimeError("job output was evicted")
            self._output.seek(offset)
            data = self._output.readline(65536)
            if (
                not self.done.is_set()
                and not data.endswith(b"\n")
                and len(data) < 65536
            ):
                return None
            # Avoid splitting a valid UTF-8 codepoint at the chunk boundary.
            if len(data) == 65536 and not data.endswith(b"\n"):
                decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
                decoder.decode(data, final=False)
                pending = decoder.getstate()[0]
                if pending:
                    data = data[: -len(pending)]
            return data

    async def events(self, offset: int = 0) -> AsyncIterator[dict[str, str]]:
        with self._lock:
            expired = self.closed
            if not 0 <= offset <= self.output_bytes:
                raise ValueError("invalid output cursor")
            self.readers += 1
        try:
            if expired:
                yield {"event": "error", "data": "job output was evicted"}
                return
            while True:
                data = await asyncio.to_thread(self._readline, offset)
                if data:
                    offset += len(data)
                    yield {
                        "id": str(offset),
                        "data": data.decode("utf-8", errors="replace").rstrip("\r\n"),
                    }
                elif data == b"" and self.done.is_set():
                    result = self.status()
                    payload = {"returncode": result["returncode"]}
                    if self.error:
                        payload["error"] = self.error
                    if "process_returncode" in result:
                        payload["process_returncode"] = result["process_returncode"]
                    yield {"event": "done", "data": json.dumps(payload)}
                    return
                else:
                    await asyncio.sleep(0.05)
        finally:
            with self._lock:
                self.readers -= 1


class JobRegistry:
    def __init__(
        self,
        *,
        max_running: int = 4,
        max_retained: int = 32,
        max_output_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        if not (0 < max_running <= max_retained and max_output_bytes > 0):
            raise ValueError("invalid job limits")
        self.max_running = max_running
        self.max_retained = max_retained
        self.max_output_bytes = max_output_bytes
        self._jobs: OrderedDict[str, ManagedJob] = OrderedDict()
        self._lock = threading.Lock()

    def submit(self, job_id: str, command: list[str], *, cwd: Path) -> ManagedJob:
        with self._lock:
            if job_id in self._jobs:
                raise ValueError("duplicate job id")
            if (
                sum(not job.done.is_set() for job in self._jobs.values())
                >= self.max_running
            ):
                raise JobCapacityError("maximum running jobs reached")
            while len(self._jobs) >= self.max_retained:
                removable = next(
                    (key for key, job in self._jobs.items() if job.close_if_idle()),
                    None,
                )
                if removable is None:
                    raise JobCapacityError(
                        "retained jobs are still active or being viewed"
                    )
                self._jobs.pop(removable)
            proc = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                start_new_session=os.name == "posix",
            )
            try:
                job = ManagedJob(
                    proc,
                    max_output_bytes=self.max_output_bytes,
                    owns_process_group=os.name == "posix",
                )
            except Exception:
                try:
                    if os.name == "posix":
                        os.killpg(proc.pid, signal.SIGKILL)
                    else:
                        proc.kill()
                except ProcessLookupError:
                    pass
                proc.wait()
                if proc.stdout is not None:
                    proc.stdout.close()
                raise
            self._jobs[job_id] = job
            return job

    def get(self, job_id: str) -> ManagedJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [
                {"job_id": key, **job.status(), "output_bytes": job.output_bytes}
                for key, job in self._jobs.items()
            ]

    def close(self) -> None:
        with self._lock:
            for job in self._jobs.values():
                job.close()
            self._jobs.clear()

    def remove(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.close()
                self._jobs.pop(job_id)
