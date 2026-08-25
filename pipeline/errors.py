"""Stable error types raised by Spiderweb pipeline boundaries."""

from __future__ import annotations


class PipelineError(Exception):
    """Base class for recoverable pipeline boundary failures."""


class BatchError(PipelineError, ValueError):
    """Base class for invalid resumable-batch operations."""


class UnknownBatchError(BatchError):
    """Raised when an operation names a batch that was never enqueued."""


class BatchInputChangedError(BatchError):
    """Raised when a resumed batch no longer matches its recorded input bytes."""
