"""Generic source-adapter SDK for Spiderweb acquisition workflows."""

from .core import (
    AcquisitionContext,
    AdapterPolicy,
    CoverageSummary,
    DownloadResult,
    PayloadRequest,
    SourceAdapterError,
    SourceEndpoint,
)
from .download import DownloadEngine, PayloadValidator
from .manifest import ManifestEngine

__all__ = [
    "AcquisitionContext",
    "AdapterPolicy",
    "CoverageSummary",
    "DownloadEngine",
    "DownloadResult",
    "ManifestEngine",
    "PayloadRequest",
    "PayloadValidator",
    "SourceAdapterError",
    "SourceEndpoint",
]
