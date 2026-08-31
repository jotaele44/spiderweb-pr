#!/usr/bin/env python3
"""Fail-closed validator for the repo-local federation spatial sidecar."""
from __future__ import annotations
import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HEX40=re.compile(r"^[a-f0-9]{40}$")
REQUIRED_CONTRACTS={"feature","layer","map_runtime","offline_package","impact_report"}

def main()->int:
 problems=[]
 path=ROOT/"federation.spatial.json"
 try: manifest=json.loads(path.read_text(encoding="utf-8"))
 except Exception as e: print(f"BLOCKED: cannot read spatial manifest: {e}"); return 1
 if manifest.get("contract_version")!="federation-spatial-manifest/1.0": problems.append("wrong contract_version")
 if manifest.get("producer_repo")!="spiderweb-pr": problems.append("producer_repo mismatch")
 if manifest.get("cross_repo",{}).get("identity_default")!="CANDIDATE_NOT_IDENTITY": problems.append("identity default must fail closed")
 if manifest.get("cross_repo",{}).get("hub_correlation_authority")!="thehub-pr": problems.append("hub correlation authority drift")
 if not HEX40.fullmatch(str(manifest.get("frozen_base_sha",""))): problems.append("invalid frozen_base_sha")
 contracts=manifest.get("contracts",{})
 if set(contracts)!=REQUIRED_CONTRACTS: problems.append("contract path set mismatch")
 for label,rel in contracts.items():
  target=ROOT/rel
  if not target.is_file(): problems.append(f"missing {label}: {rel}")
  else:
   try: json.loads(target.read_text(encoding="utf-8"))
   except Exception as e: problems.append(f"invalid JSON schema {rel}: {e}")
 for key in ("postgis_migration","mvt_migration"):
  rel=manifest.get("storage",{}).get(key)
  if not rel or not (ROOT/rel).is_file(): problems.append(f"missing storage artifact: {key}")
 if manifest.get("storage",{}).get("ownership")!="REPO_LOCAL": problems.append("storage ownership must be REPO_LOCAL")
 if problems:
  print(json.dumps({"ok":False,"problems":problems},indent=2)); return 1
 print(json.dumps({"ok":True,"producer_repo":"spiderweb-pr","contract":"federation-spatial-contract/1.0"},indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
