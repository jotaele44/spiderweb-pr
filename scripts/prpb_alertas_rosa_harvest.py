#!/usr/bin/env python3
"""PRPB Plan ROSA (missing/kidnapped women 18+ in dangerous circumstances)
harvester.

Operator drops per-incident HTML pages under::

    data/sources/prpb_alertas_rosa/<YYYY-MM-DD>/<alert_id>.html

ROSA is a sex-coded plan (women only), so ``EXPECTED_SEX = "F"`` overrides
whatever the parser would have read from the page. See
``scripts/_prpb_alertas_base.py`` for the shared parser.
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._prpb_alertas_base import PrpbAlertasBase  # noqa: E402


class PrpbAlertasRosaHarvest(PrpbAlertasBase):
    SOURCE_ID = "prpb_alertas_rosa"
    PLAN_MATCH = "ROSA"
    INCIDENT_CLASS = "endangered_woman"
    EXPECTED_SEX = "F"
    RAW_ALIASES = {}


if __name__ == "__main__":
    raise SystemExit(PrpbAlertasRosaHarvest().main())
