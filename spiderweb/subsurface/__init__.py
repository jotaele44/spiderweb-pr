"""Reusable AOI-driven subsurface relevance analysis.

Spatial proximity is discovery, not identity or connectivity proof. Public-source
completeness is controlled by the frozen source denominator and family ledger.

The package-level names load on first use through the module ``__getattr__`` below,
so importing a submodule such as ``spiderweb.subsurface.evidence`` does not pull in
``aoi`` and its shapely dependency. The access-point lane of
``scripts/federation_export.py`` relies on that: the hub runs that export with only
its own packages installed.
"""

from __future__ import annotations

from typing import Any

_EXPORTS = {
    "FrozenAOI": "aoi",
    "freeze_aoi": "aoi",
    "EvidenceRecord": "evidence",
    "EvidenceTier": "evidence",
    "SpatialState": "evidence",
    "adjudicate_feature": "evidence",
    "validate_records": "evidence",
    "AuthoritativeSourceRunner": "runner",
    "FamilyCertification": "runner",
    "SourceLedgerRow": "runner",
    "DEFAULT_SOURCES": "sources",
    "SourceKind": "sources",
    "SourceSpec": "sources",
    "SourceStatus": "sources",
    "denominator_sha256": "sources",
}


def __getattr__(name: str) -> Any:  # PEP 562: load submodules on first use
    # One explicit import per submodule, so static analysers such as PyInstaller
    # still see every module the package can load.
    module_name = _EXPORTS.get(name)
    if module_name == "aoi":
        from . import aoi as module
    elif module_name == "evidence":
        from . import evidence as module
    elif module_name == "runner":
        from . import runner as module
    elif module_name == "sources":
        from . import sources as module
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(module, name)


__all__ = [
    "AuthoritativeSourceRunner",
    "DEFAULT_SOURCES",
    "EvidenceRecord",
    "EvidenceTier",
    "FamilyCertification",
    "FrozenAOI",
    "SourceKind",
    "SourceLedgerRow",
    "SourceSpec",
    "SourceStatus",
    "SpatialState",
    "adjudicate_feature",
    "denominator_sha256",
    "freeze_aoi",
    "validate_records",
]
