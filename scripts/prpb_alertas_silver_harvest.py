#!/usr/bin/env python3
"""PRPB Plan SILVER (persons with cognitive impairment — Alzheimer's,
dementia, similar) harvester.

Operator drops per-incident HTML pages under::

    data/sources/prpb_alertas_silver/<YYYY-MM-DD>/<alert_id>.html

SILVER is not sex-coded; the parser reads sex from the page text. See
``scripts/_prpb_alertas_base.py`` for the shared parser.
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._prpb_alertas_base import PrpbAlertasBase  # noqa: E402


class PrpbAlertasSilverHarvest(PrpbAlertasBase):
    SOURCE_ID = "prpb_alertas_silver"
    PLAN_MATCH = "SILVER"
    INCIDENT_CLASS = "cognitive_impairment"
    EXPECTED_SEX = ""
    RAW_ALIASES = {}


if __name__ == "__main__":
    raise SystemExit(PrpbAlertasSilverHarvest().main())
