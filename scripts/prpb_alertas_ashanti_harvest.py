#!/usr/bin/env python3
"""PRPB Plan ASHANTI (missing/kidnapped adults 18+ in dangerous circumstances
not covered by AMBER/ROSA/SILVER) harvester.

Operator drops per-incident HTML pages under::

    data/sources/prpb_alertas_ashanti/<YYYY-MM-DD>/<alert_id>.html

See ``scripts/_prpb_alertas_base.py`` for the shared parser.
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._prpb_alertas_base import PrpbAlertasBase  # noqa: E402


class PrpbAlertasAshantiHarvest(PrpbAlertasBase):
    SOURCE_ID = "prpb_alertas_ashanti"
    PLAN_MATCH = "ASHANTI"
    INCIDENT_CLASS = "endangered_adult"
    EXPECTED_SEX = ""
    RAW_ALIASES = {}


if __name__ == "__main__":
    raise SystemExit(PrpbAlertasAshantiHarvest().main())
