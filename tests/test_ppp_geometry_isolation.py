"""Repository-isolation regression gates for the PPP geometry lane."""
from __future__ import annotations

import pytest

from readiness import ppp_geometry as pg


def test_default_resolution_does_not_discover_sibling_checkout():
    with pytest.raises(pg.PPPGeometryError, match="explicit moneysweep export package required"):
        pg.resolve_projects()
