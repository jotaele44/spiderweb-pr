#!/usr/bin/env python3
"""PRPB Plan AMBER (kidnapped minors under 18) harvester.

Operator drops per-incident HTML pages under::

    data/sources/prpb_alertas_amber/<YYYY-MM-DD>/<alert_id>.html

This harvester reads them, redacts (names dropped, alert_id hashed),
normalizes dates / age / status, and emits the canonical CSV.

See ``scripts/_prpb_alertas_base.py`` for the shared parser.
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._prpb_alertas_base import PrpbAlertasBase  # noqa: E402


class PrpbAlertasAmberHarvest(PrpbAlertasBase):
    SOURCE_ID = "prpb_alertas_amber"
    PLAN_MATCH = "AMBER"
    INCIDENT_CLASS = "missing_juvenile"
    EXPECTED_SEX = ""        # AMBER is for minors of any sex; parse from text
    RAW_ALIASES = {}         # HTML, not CSV — base.harvest is overridden


if __name__ == "__main__":
    raise SystemExit(PrpbAlertasAmberHarvest().main())
