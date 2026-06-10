# Duplication Register

Tracks files that intentionally exist in more than one federation repo, with a declared
canonical owner and a removal condition. A duplicate is tolerable **only** while listed here.

| File | Also in | Canonical owner (going forward) | Status | Removal condition |
|------|---------|----------------------------------|--------|-------------------|
| `integration/ilap_airspace_bridge.py` | `../skywatcher-pr/ilap_airspace_bridge.py` | **skywatcher-pr** (airspace domain) | temporary | Remove spiderweb's copy once its phase-2 / `release_check` airspace export is reconciled onto skywatcher-pr |
| `integration/aasb_airspace_bridge.py` | `../skywatcher-pr/aasb_airspace_bridge.py` | **skywatcher-pr** (airspace domain) | temporary | Same as above |

## Context
Airspace ingestion (the `fr24/` screenshot pipeline + RLSM suite) migrated to
[`skywatcher-pr`](https://github.com/jotaele44/skywatcher-pr) in 2026-06 (spiderweb PRs
#110/#111). The ILAP/AASB airspace bridges are duplicated: skywatcher-pr carries them as
the airspace producer, while spiderweb-pr still calls **its** copies in live paths:
- `run_all.py` phase 2 (`run_phase_2` → `export_spiderweb`)
- `release_check.py` (`export_spiderweb`)

Because spiderweb's copies are still live, they are **not** deleted here. The long-term
owner is skywatcher-pr; spiderweb's copies should be removed once spiderweb's own airspace
export path is either retired or pointed at skywatcher's output.

Do not extend the duplicated files; make airspace-bridge changes in the canonical owner.
