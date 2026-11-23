"""Geospatial Visualization Engine: reproducible, source-bound maps, sections and 3D scenes.

One engine consumes frozen, hash-pinned snapshots of already-wired data and
renders three views (top-down, vertical section, 3D) with a machine-readable
receipt.  A rendered picture is never evidence of a connection: connections are
drawn according to their declared evidence class and every run is validated.

See docs/GEOSPATIAL_VISUALIZATION_ENGINE.md.
"""

from __future__ import annotations

VERSION = "0.1.0"
RENDERER = "spiderweb-viz-engine"
EVIDENCE_CLASSES = ("observed", "inferred", "modeled", "unknown")
