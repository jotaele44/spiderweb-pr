"""Central YAML config loader with light validation (T10-85).

The ``configs/*.yaml`` registries were each loaded ad-hoc. This module gives one
fail-closed entry point: it parses a YAML file, confirms it is a mapping, and
optionally checks that required top-level keys are present. No heavy schema
dependency — just enough validation to turn a malformed config into a clear
error instead of a downstream ``KeyError``.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


class ConfigError(ValueError):
    """Raised when a config file is missing, unparseable, or fails validation."""


# ── Compatibility aliases (poi -> pin migration, stage 1) ────────────────────
# Deprecated config filenames mapped to their canonical replacements. When a
# caller requests the old name and it no longer exists on disk, we transparently
# resolve to the new file and emit a DeprecationWarning, so stragglers and
# external references keep working through the transition.
DEPRECATED_CONFIG_ALIASES: Dict[str, str] = {
    "poi_registry.yaml": "pin_registry.yaml",
}

# Legacy top-level keys aliased to their canonical names. After load we mirror
# the two vocabularies so callers reading either key keep working; reading a
# legacy key warns, exposing the new key back to legacy callers is silent.
DEPRECATED_KEY_ALIASES: Dict[str, str] = {
    "poi_taxonomy": "pin_taxonomy",
    "poi_records": "pin_records",
}


def _resolve_deprecated_path(p: Path) -> Path:
    """Map a deprecated config path to its canonical file, warning if used."""
    new_name = DEPRECATED_CONFIG_ALIASES.get(p.name)
    if new_name is None:
        return p
    candidate = p.with_name(new_name)
    if not p.exists() and candidate.exists():
        warnings.warn(
            f"config '{p.name}' is deprecated; loading '{new_name}' instead",
            DeprecationWarning,
            stacklevel=3,
        )
        return candidate
    return p


def _normalize_deprecated_keys(data: Dict[str, Any]) -> None:
    """Mirror legacy/canonical key pairs in-place so either vocabulary resolves."""
    for old, new in DEPRECATED_KEY_ALIASES.items():
        if old in data and new not in data:
            warnings.warn(
                f"config key '{old}' is deprecated; use '{new}'",
                DeprecationWarning,
                stacklevel=3,
            )
            data[new] = data[old]
        elif new in data and old not in data:
            data[old] = data[new]


def load_yaml_config(
    path: str | Path,
    *,
    required_keys: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Load and validate a YAML config file.

    Args:
        path: path to the ``.yaml`` file.
        required_keys: top-level keys that must be present (optional).

    Returns:
        The parsed mapping.

    Raises:
        ConfigError: file missing, not valid YAML, not a mapping, or missing a
            required key.
    """
    p = _resolve_deprecated_path(Path(path))
    if not p.exists():
        raise ConfigError(f"config not found: {p}")

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - PyYAML ships in the airspace extra
        raise ConfigError("PyYAML is required to load configs") from exc

    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {p}: {exc}") from exc

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"config {p} must be a mapping, got {type(data).__name__}")

    _normalize_deprecated_keys(data)

    if required_keys:
        missing = [k for k in required_keys if k not in data]
        if missing:
            raise ConfigError(f"config {p} missing required keys: {missing}")

    return data
