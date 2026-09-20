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

if [[ "$(git rev-parse --show-toplevel)" != "$ROOT" ]]; then
  echo "FAIL: runtime closure must execute from the repository checkout"
  exit 3
fi

HEAD_SHA="$(git rev-parse HEAD)"
HEAD_REF="$(git symbolic-ref --quiet --short HEAD || echo DETACHED_HEAD)"
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  echo "FAIL: runtime closure requires a clean Git worktree"
  git status --short
  exit 3
fi

mkdir -p "$OUT"/{audit,queries,plans,fetch,closure,ssurgo,packages,reference}

echo "=== LOCATION_QUERY RUNTIME CLOSURE ==="
echo "RUN_ID=$RUN_ID"
echo "ROOT=$ROOT"
echo "OUT=$OUT"
echo "GIT_HEAD_SHA=$HEAD_SHA"
echo "GIT_HEAD_REF=$HEAD_REF"
echo "SOURCE_REDOWNLOAD_POLICY=MISSING_OR_NEW_SNAPSHOT_ONLY"
echo "AUTO_PROVIDER_PROMOTION=FALSE"
echo "AUTO_MERGE=FALSE"

# ---------------------------------------------------------------------------
# Preflight — fail before network if the checkout/runtime is incomplete.
# ---------------------------------------------------------------------------

for required in \
  configs/location_query_providers.json \
  configs/location_query_reference_aois.json \
  configs/location_query_source_bindings.json \
  configs/ssurgo_component_children.json \
  scripts/location_query.py \
  scripts/location_query_fetch.py \
  scripts/location_query_package.py \
  scripts/close_location_query_denominators.py \
  scripts/location_query_ssurgo.py
do
  if [[ ! -f "$ROOT/$required" ]]; then
    echo "FAIL: required runtime artifact missing: $required"
    exit 4
  fi
done

python - <<'PY'
import importlib.util
import sys

required = ["geopandas", "pyproj", "shapely"]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit(
        "FAIL: missing geo runtime dependencies: "
        + ", ".join(missing)
        + "; install with pip install -e '.[geo,dev]'"
    )
if sys.version_info < (3, 11):
    raise SystemExit("FAIL: Python >= 3.11 required")
print("PREFLIGHT_PYTHON_GEO=PASS")
PY

python -m py_compile \
  spiderweb/location_query.py \
  spiderweb/location_query_sources.py \
  spiderweb/ssurgo_chain.py \
  spiderweb/provider_denominators.py \
  spiderweb/denominator_chain.py \
  spiderweb/denominator_closure.py \
  scripts/location_query.py \
  scripts/location_query_fetch.py \
  scripts/location_query_package.py \
  scripts/close_location_query_denominators.py \
  scripts/location_query_ssurgo.py

echo "PREFLIGHT_SYNTAX=PASS"

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

set +e
python scripts/location_query_fetch.py   "$OUT/plans/provider_denominators.acquisition_plan.json"   --output-dir "$OUT/fetch/provider_denominators"   --discovery-only   > "$OUT/audit/provider_denominators_fetch_stdout.json"
DISCOVERY_FETCH_EXIT=$?
set -e

if [[ ! -f "$OUT/fetch/provider_denominators/fetch_receipt.json" ]]; then
  echo "FAIL: discovery fetch produced no receipt"
  exit 5
fi

set +e
python scripts/location_query_package.py   "$OUT/plans/provider_denominators.acquisition_plan.json"   "$OUT/fetch/provider_denominators/fetch_receipt.json"   --output "$OUT/packages/provider_denominators.package.json"   > "$OUT/audit/provider_denominators_package_stdout.json"
DISCOVERY_PACKAGE_EXIT=$?

python scripts/close_location_query_denominators.py   --fetch-receipt "$OUT/fetch/provider_denominators/fetch_receipt.json"   --query "$OUT/queries/provider_denominators.json"   --output-dir "$OUT/closure/provider_denominators"   > "$OUT/audit/provider_denominator_closure_stdout.json"
DISCOVERY_CLOSURE_EXIT=$?
set -e

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

set +e
python scripts/location_query_fetch.py   "$OUT/plans/hucar_ssurgo.acquisition_plan.json"   --output-dir "$OUT/fetch/hucar_ssurgo"   --discovery-only   > "$OUT/audit/hucar_ssurgo_spatial_fetch_stdout.json"
SSURGO_SPATIAL_FETCH_EXIT=$?

SSURGO_SPATIAL_PACKAGE_EXIT=5
SSURGO_STAGE2_PLAN_EXIT=5
SSURGO_STAGE2_FETCH_EXIT=5
SSURGO_STAGE2_PACKAGE_EXIT=5
SSURGO_STAGE3_PLAN_EXIT=5
SSURGO_STAGE3_FETCH_EXIT=5
SSURGO_STAGE3_PACKAGE_EXIT=5
SSURGO_STAGE3_CERT_EXIT=5

if [[ -f "$OUT/fetch/hucar_ssurgo/fetch_receipt.json" ]]; then
  python scripts/location_query_package.py     "$OUT/plans/hucar_ssurgo.acquisition_plan.json"     "$OUT/fetch/hucar_ssurgo/fetch_receipt.json"     --output "$OUT/packages/hucar_ssurgo_spatial.package.json"     > "$OUT/audit/hucar_ssurgo_spatial_package_stdout.json"
  SSURGO_SPATIAL_PACKAGE_EXIT=$?
fi

if [[ -f "$OUT/fetch/hucar_ssurgo/002_SSURGO_SOILS_MapunitPoly.raw" && -f "$OUT/fetch/hucar_ssurgo/002_SSURGO_SOILS_MapunitPoly.json" ]]; then
  python scripts/ssurgo_location_stage2.py     --query "$OUT/queries/hucar_ssurgo.json"     --mapunitpoly-raw "$OUT/fetch/hucar_ssurgo/002_SSURGO_SOILS_MapunitPoly.raw"     --mapunitpoly-receipt "$OUT/fetch/hucar_ssurgo/002_SSURGO_SOILS_MapunitPoly.json"     --output "$OUT/plans/hucar_ssurgo.stage2.json"     > "$OUT/audit/hucar_ssurgo_stage2_plan_stdout.json"
  SSURGO_STAGE2_PLAN_EXIT=$?
fi

if [[ "$SSURGO_STAGE2_PLAN_EXIT" -eq 0 && -f "$OUT/plans/hucar_ssurgo.stage2.json" ]]; then
  python scripts/location_query_fetch.py     "$OUT/plans/hucar_ssurgo.stage2.json"     --output-dir "$OUT/fetch/hucar_ssurgo_stage2"     > "$OUT/audit/hucar_ssurgo_stage2_fetch_stdout.json"
  SSURGO_STAGE2_FETCH_EXIT=$?

  if [[ -f "$OUT/fetch/hucar_ssurgo_stage2/fetch_receipt.json" ]]; then
    python scripts/location_query_package.py       "$OUT/plans/hucar_ssurgo.stage2.json"       "$OUT/fetch/hucar_ssurgo_stage2/fetch_receipt.json"       --output "$OUT/packages/hucar_ssurgo_stage2.package.json"       > "$OUT/audit/hucar_ssurgo_stage2_package_stdout.json"
    SSURGO_STAGE2_PACKAGE_EXIT=$?
  fi
fi

if [[ "$SSURGO_STAGE2_FETCH_EXIT" -eq 0 && -f "$OUT/fetch/hucar_ssurgo_stage2/002_SSURGO_SOILS_component.raw" && -f "$OUT/fetch/hucar_ssurgo_stage2/002_SSURGO_SOILS_component.json" ]]; then
  python scripts/ssurgo_location_stage3.py     --query "$OUT/queries/hucar_ssurgo.json"     --component-raw "$OUT/fetch/hucar_ssurgo_stage2/002_SSURGO_SOILS_component.raw"     --component-receipt "$OUT/fetch/hucar_ssurgo_stage2/002_SSURGO_SOILS_component.json"     --stage2-plan "$OUT/plans/hucar_ssurgo.stage2.json"     --children configs/ssurgo_component_children.json     --output "$OUT/plans/hucar_ssurgo.stage3.json"     > "$OUT/audit/hucar_ssurgo_stage3_plan_stdout.json"
  SSURGO_STAGE3_PLAN_EXIT=$?
fi

if [[ "$SSURGO_STAGE3_PLAN_EXIT" -eq 0 && -f "$OUT/plans/hucar_ssurgo.stage3.json" ]]; then
  python scripts/location_query_fetch.py     "$OUT/plans/hucar_ssurgo.stage3.json"     --output-dir "$OUT/fetch/hucar_ssurgo_stage3"     > "$OUT/audit/hucar_ssurgo_stage3_fetch_stdout.json"
  SSURGO_STAGE3_FETCH_EXIT=$?

  if [[ -f "$OUT/fetch/hucar_ssurgo_stage3/fetch_receipt.json" ]]; then
    python scripts/location_query_package.py       "$OUT/plans/hucar_ssurgo.stage3.json"       "$OUT/fetch/hucar_ssurgo_stage3/fetch_receipt.json"       --output "$OUT/packages/hucar_ssurgo_stage3.package.json"       > "$OUT/audit/hucar_ssurgo_stage3_package_stdout.json"
    SSURGO_STAGE3_PACKAGE_EXIT=$?
  fi
fi

if [[ "$SSURGO_STAGE3_FETCH_EXIT" -eq 0 && -f "$OUT/fetch/hucar_ssurgo_stage3/fetch_receipt.json" ]]; then
  python scripts/certify_ssurgo_stage3.py     --stage3-plan "$OUT/plans/hucar_ssurgo.stage3.json"     --fetch-receipt "$OUT/fetch/hucar_ssurgo_stage3/fetch_receipt.json"     --output "$OUT/ssurgo/SSURGO_STAGE3_CERTIFICATION.json"     > "$OUT/audit/hucar_ssurgo_stage3_certification_stdout.json"
  SSURGO_STAGE3_CERT_EXIT=$?
fi

set -e

# ---------------------------------------------------------------------------
# Phase 4 — final snapshot manifest.
# Hash every regular file created in this run. This is a manifestation ledger,
# not an aggregate identity claim for heterogeneous semantic records.
# ---------------------------------------------------------------------------

export OUT HEAD_SHA HEAD_REF DISCOVERY_FETCH_EXIT DISCOVERY_PACKAGE_EXIT DISCOVERY_CLOSURE_EXIT SSURGO_SPATIAL_FETCH_EXIT SSURGO_SPATIAL_PACKAGE_EXIT SSURGO_STAGE2_PLAN_EXIT SSURGO_STAGE2_FETCH_EXIT SSURGO_STAGE2_PACKAGE_EXIT SSURGO_STAGE3_PLAN_EXIT SSURGO_STAGE3_FETCH_EXIT SSURGO_STAGE3_PACKAGE_EXIT SSURGO_STAGE3_CERT_EXIT
python - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["OUT"])
head_sha = os.environ["HEAD_SHA"]
head_ref = os.environ["HEAD_REF"]
phase_exit_codes = {
    "discovery_fetch": int(os.environ["DISCOVERY_FETCH_EXIT"]),
    "discovery_package": int(os.environ["DISCOVERY_PACKAGE_EXIT"]),
    "discovery_closure": int(os.environ["DISCOVERY_CLOSURE_EXIT"]),
    "ssurgo_spatial_fetch": int(os.environ["SSURGO_SPATIAL_FETCH_EXIT"]),
    "ssurgo_spatial_package": int(os.environ["SSURGO_SPATIAL_PACKAGE_EXIT"]),
    "ssurgo_stage2_plan": int(os.environ["SSURGO_STAGE2_PLAN_EXIT"]),
    "ssurgo_stage2_fetch": int(os.environ["SSURGO_STAGE2_FETCH_EXIT"]),
    "ssurgo_stage2_package": int(os.environ["SSURGO_STAGE2_PACKAGE_EXIT"]),
    "ssurgo_stage3_plan": int(os.environ["SSURGO_STAGE3_PLAN_EXIT"]),
    "ssurgo_stage3_fetch": int(os.environ["SSURGO_STAGE3_FETCH_EXIT"]),
    "ssurgo_stage3_package": int(os.environ["SSURGO_STAGE3_PACKAGE_EXIT"]),
    "ssurgo_stage3_certification": int(os.environ["SSURGO_STAGE3_CERT_EXIT"]),
}
overall_state = (
    "PASS"
    if all(value == 0 for value in phase_exit_codes.values())
    else "PARTIAL_OR_BLOCKED"
)

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
    "state": overall_state,
    "run_id": root.name,
    "phase_exit_codes": phase_exit_codes,
    "git_head_sha": head_sha,
    "git_head_ref": head_ref,
    "artifact_count": len(records),
    "records": records,
    "invariants": {
        "snapshot_path_unique": len(records) == len({row["relative_path"] for row in records}),
        "raw_and_derived_manifestations_kept_separate": True,
        "aggregate_hash_not_used_as_cross_schema_identity": True,
        "automatic_provider_promotion": False,
        "automatic_merge": False,
        "clean_git_worktree_required": True,
        "source_code_manifestation_bound_to_git_sha": True,
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
echo "SNAPSHOT=$OUT"
if [[ "$DISCOVERY_FETCH_EXIT" -eq 0 && "$DISCOVERY_PACKAGE_EXIT" -eq 0 && "$DISCOVERY_CLOSURE_EXIT" -eq 0 && "$SSURGO_SPATIAL_FETCH_EXIT" -eq 0 && "$SSURGO_SPATIAL_PACKAGE_EXIT" -eq 0 && "$SSURGO_STAGE2_PLAN_EXIT" -eq 0 && "$SSURGO_STAGE2_FETCH_EXIT" -eq 0 && "$SSURGO_STAGE2_PACKAGE_EXIT" -eq 0 && "$SSURGO_STAGE3_PLAN_EXIT" -eq 0 && "$SSURGO_STAGE3_FETCH_EXIT" -eq 0 && "$SSURGO_STAGE3_PACKAGE_EXIT" -eq 0 && "$SSURGO_STAGE3_CERT_EXIT" -eq 0 ]]; then
  echo "LOCATION_QUERY_RUNTIME_CLOSURE_RUN=PASS"
  echo "NEXT_GATE=ADJUDICATE_RUNTIME_RECEIPTS_AND_PROVIDER_PROMOTIONS"
  exit 0
else
  echo "LOCATION_QUERY_RUNTIME_CLOSURE_RUN=PARTIAL_OR_BLOCKED"
  echo "DISCOVERY_FETCH_EXIT=$DISCOVERY_FETCH_EXIT"
  echo "DISCOVERY_PACKAGE_EXIT=$DISCOVERY_PACKAGE_EXIT"
  echo "DISCOVERY_CLOSURE_EXIT=$DISCOVERY_CLOSURE_EXIT"
  echo "SSURGO_SPATIAL_FETCH_EXIT=$SSURGO_SPATIAL_FETCH_EXIT"
  echo "SSURGO_SPATIAL_PACKAGE_EXIT=$SSURGO_SPATIAL_PACKAGE_EXIT"
  echo "SSURGO_STAGE2_PLAN_EXIT=$SSURGO_STAGE2_PLAN_EXIT"
  echo "SSURGO_STAGE2_FETCH_EXIT=$SSURGO_STAGE2_FETCH_EXIT"
  echo "SSURGO_STAGE2_PACKAGE_EXIT=$SSURGO_STAGE2_PACKAGE_EXIT"
  echo "SSURGO_STAGE3_PLAN_EXIT=$SSURGO_STAGE3_PLAN_EXIT"
  echo "SSURGO_STAGE3_FETCH_EXIT=$SSURGO_STAGE3_FETCH_EXIT"
  echo "SSURGO_STAGE3_PACKAGE_EXIT=$SSURGO_STAGE3_PACKAGE_EXIT"
  echo "SSURGO_STAGE3_CERT_EXIT=$SSURGO_STAGE3_CERT_EXIT"
  echo "NEXT_GATE=ADJUDICATE_PARTIAL_RUNTIME_EVIDENCE"
  exit 1
fi
