#!/usr/bin/env bash
set -euo pipefail

# Restartable LOCATION_QUERY runtime closure runner.
#
# This script intentionally does not mutate configs/location_query_providers.json,
# does not merge PRs, and never overwrites an existing snapshot. Each run gets a
# caller-supplied RUN_ID so mutable provider responses remain versioned evidence.
#
# Usage:
#   scripts/run_location_query_runtime_closure.sh RUN_ID
#
# Recommended environment:
#   python >= 3.11
#   pip install -e '.[geo,dev]'
#
# Phases:
#   1. offline/static audits + reference planning
#   2. discovery-only denominator acquisition
#   3. offline denominator closure/adjudication
#   4. SSURGO Hucar resolver-stage acquisition + full 22-child continuation
#   5. package manifests
#
# No provider status is auto-promoted by this script.

RUN_ID="${1:-}"
if [[ -z "$RUN_ID" ]]; then
  echo "FAIL: RUN_ID required"
  exit 2
fi

case "$RUN_ID" in
  *[!A-Za-z0-9._-]*)
    echo "FAIL: RUN_ID may contain only A-Z a-z 0-9 . _ -"
    exit 2
    ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT="$ROOT/outputs/location_query/runtime_closure/$RUN_ID"
if [[ -e "$OUT" ]]; then
  echo "FAIL: snapshot already exists: $OUT"
  echo "Use a new RUN_ID. Existing snapshots are immutable."
  exit 3
fi
mkdir -p "$OUT"/{audit,queries,plans,fetch,closure,ssurgo,packages,reference}

echo "=== LOCATION_QUERY RUNTIME CLOSURE ==="
echo "RUN_ID=$RUN_ID"
echo "ROOT=$ROOT"
echo "OUT=$OUT"
echo "SOURCE_REDOWNLOAD_POLICY=MISSING_OR_NEW_SNAPSHOT_ONLY"
echo "AUTO_PROVIDER_PROMOTION=FALSE"
echo "AUTO_MERGE=FALSE"

# ---------------------------------------------------------------------------
# Phase 1 — offline audits and frozen planning corpus
# ---------------------------------------------------------------------------

python scripts/audit_location_query_registry.py   > "$OUT/audit/registry_audit.json"

python scripts/audit_location_query_static.py   > "$OUT/audit/static_audit.json"

python scripts/run_location_query_reference_corpus.py   --output-dir "$OUT/reference/plans"   > "$OUT/audit/reference_corpus_stdout.json"

# ---------------------------------------------------------------------------
# Phase 2 — provider denominator discovery.
# Use a bounded Puerto Rico reference AOI. Metadata denominators are provider
# manifestations; the AOI does not become part of their canonical identity.
# ---------------------------------------------------------------------------

cat > "$OUT/queries/provider_denominators.json" <<'JSON'
{
  "query_id": "provider_denominator_discovery",
  "geometry": {
    "type": "bbox",
    "west": -67.35,
    "south": 17.80,
    "east": -65.20,
    "north": 18.60,
    "crs": "EPSG:4326"
  },
  "families": [
    "hydrography",
    "flood_hazard",
    "federal_infrastructure"
  ],
  "mode": "plan",
  "allow_partial": false
}
JSON

python scripts/location_query.py   "$OUT/queries/provider_denominators.json"   --out "$OUT/plans/provider_denominators.acquisition_plan.json"   > "$OUT/audit/provider_denominators_plan_stdout.json"

python scripts/location_query_fetch.py   "$OUT/plans/provider_denominators.acquisition_plan.json"   --output-dir "$OUT/fetch/provider_denominators"   --discovery-only   > "$OUT/audit/provider_denominators_fetch_stdout.json"

python scripts/location_query_package.py   "$OUT/plans/provider_denominators.acquisition_plan.json"   "$OUT/fetch/provider_denominators/fetch_receipt.json"   --output "$OUT/packages/provider_denominators.package.json"   > "$OUT/audit/provider_denominators_package_stdout.json"

python scripts/close_location_query_denominators.py   --fetch-receipt "$OUT/fetch/provider_denominators/fetch_receipt.json"   --query "$OUT/queries/provider_denominators.json"   --output-dir "$OUT/closure/provider_denominators"   > "$OUT/audit/provider_denominator_closure_stdout.json"

# ---------------------------------------------------------------------------
# Phase 3 — SSURGO Hucar reference AOI.
# Stage 1 is resolver-stage WFS. The continuation performs exact spatial
# selection, MUKEY -> mapunit/component -> COKEY -> current 22 child tables.
# ---------------------------------------------------------------------------

cat > "$OUT/queries/hucar_ssurgo.json" <<'JSON'
{
  "query_id": "hucar_2km_ssurgo",
  "geometry": {
    "type": "radius",
    "lat": 18.0119,
    "lon": -66.2396,
    "radius_m": 2000
  },
  "families": ["soils"],
  "mode": "plan",
  "allow_partial": false
}
JSON

python scripts/location_query.py   "$OUT/queries/hucar_ssurgo.json"   --out "$OUT/plans/hucar_ssurgo.acquisition_plan.json"   > "$OUT/audit/hucar_ssurgo_plan_stdout.json"

python scripts/location_query_fetch.py   "$OUT/plans/hucar_ssurgo.acquisition_plan.json"   --output-dir "$OUT/fetch/hucar_ssurgo"   --discovery-only   > "$OUT/audit/hucar_ssurgo_spatial_fetch_stdout.json"

python scripts/location_query_package.py   "$OUT/plans/hucar_ssurgo.acquisition_plan.json"   "$OUT/fetch/hucar_ssurgo/fetch_receipt.json"   --output "$OUT/packages/hucar_ssurgo_spatial.package.json"   > "$OUT/audit/hucar_ssurgo_spatial_package_stdout.json"

python scripts/location_query_ssurgo.py   "$OUT/plans/hucar_ssurgo.acquisition_plan.json"   "$OUT/fetch/hucar_ssurgo/fetch_receipt.json"   --children configs/ssurgo_component_children.json   --output-dir "$OUT/ssurgo/hucar_2km"   > "$OUT/audit/hucar_ssurgo_continuation_stdout.json"

# ---------------------------------------------------------------------------
# Phase 4 — final snapshot manifest.
# Hash every regular file created in this run. This is a manifestation ledger,
# not an aggregate identity claim for heterogeneous semantic records.
# ---------------------------------------------------------------------------

export OUT
python - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["OUT"])

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

manifest_path = root / "RUNTIME_CLOSURE_MANIFEST.json"
records = []
for path in sorted(root.rglob("*")):
    if not path.is_file() or path == manifest_path:
        continue
    records.append({
        "relative_path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    })

manifest = {
    "schema_version": "spiderweb.location_query_runtime_closure_manifest.v1.0",
    "state": "PASS",
    "run_id": root.name,
    "artifact_count": len(records),
    "records": records,
    "invariants": {
        "snapshot_path_unique": len(records) == len({row["relative_path"] for row in records}),
        "raw_and_derived_manifestations_kept_separate": True,
        "aggregate_hash_not_used_as_cross_schema_identity": True,
        "automatic_provider_promotion": False,
        "automatic_merge": False,
    },
}
manifest_path.write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(json.dumps({
    "state": "PASS",
    "artifact_count": len(records),
    "manifest": str(manifest_path),
    "manifest_sha256": sha256(manifest_path),
}, indent=2, sort_keys=True))
PY

echo
echo "LOCATION_QUERY_RUNTIME_CLOSURE_RUN=PASS"
echo "SNAPSHOT=$OUT"
echo "NEXT_GATE=ADJUDICATE_RUNTIME_RECEIPTS_AND_PROVIDER_PROMOTIONS"
