from pathlib import Path

import pytest

from pipeline.errors import BatchInputChangedError, UnknownBatchError
from pipeline.hardening_layer import ResumableJobQueue


def test_resume_rejects_changed_batch_inputs(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"first")
    queue = ResumableJobQueue(str(tmp_path / "queue.db"))
    queue.enqueue_batch([str(image)], "batch-1")
    queue.save_checkpoint("batch-1", completed=0, failed=0)

    image.write_bytes(b"changed")

    with pytest.raises(BatchInputChangedError, match="inputs changed"):
        queue.resume_batch("batch-1")


def test_resume_returns_pending_jobs_when_inputs_match(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"stable")
    queue = ResumableJobQueue(str(tmp_path / "queue.db"))
    queue.enqueue_batch([str(image)], "batch-1")
    queue.save_checkpoint("batch-1", completed=0, failed=0)

    jobs = queue.resume_batch("batch-1")

    assert [job["image_path"] for job in jobs] == [str(image)]


def test_checkpoint_and_resume_unknown_batch_raise_typed_error(tmp_path: Path) -> None:
    queue = ResumableJobQueue(str(tmp_path / "queue.db"))

    with pytest.raises(UnknownBatchError, match="unknown batch"):
        queue.save_checkpoint("missing", completed=0, failed=0)
    with pytest.raises(UnknownBatchError, match="unknown batch"):
        queue.resume_batch("missing")
