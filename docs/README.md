# Documentation index

A subsystem-grouped map of the ~50 docs in this directory (T12-93). Start with
the [root README](../README.md) and [QUICK_START](QUICK_START.md), then dive into
the relevant subsystem below.

## Getting started
- [QUICK_START.md](QUICK_START.md) — install + first run
- [EXECUTION_GUIDE.md](EXECUTION_GUIDE.md) — running the pipeline end to end
- [ARCHITECTURE.md](ARCHITECTURE.md) — system architecture (phases 0–4, federation, RLSM)
- [TESTING.md](TESTING.md) — test tiers and how to run them
- [RELEASE_READINESS.md](RELEASE_READINESS.md) — the release gate

## Roadmap & planning
- [NEXT_100_TASKS_V2.md](NEXT_100_TASKS_V2.md) — the active 100-task roadmap
- [ROI_TASK_LEDGER.md](ROI_TASK_LEDGER.md) — completed-work ledger
- [archive_reuse_triage.md](archive_reuse_triage.md)

## Contracts, schema & validation
- [SCHEMA_AND_EXPORT_CONTRACTS.md](SCHEMA_AND_EXPORT_CONTRACTS.md)
- [ARTIFACT_MANIFEST_STANDARD.md](ARTIFACT_MANIFEST_STANDARD.md)
- [airspace_schema.md](airspace_schema.md)
- [export_contract.md](export_contract.md)
- [validation_gates.md](validation_gates.md)
- [confidence_model.md](confidence_model.md)
- [lineage_model.md](lineage_model.md)
- [contracts/](contracts) — per-artifact contract docs

## Federation
- [federation_readiness.md](federation_readiness.md)
- [CONTRACT_FINANCE_PRODUCTION_FUSION_RECIPE.md](CONTRACT_FINANCE_PRODUCTION_FUSION_RECIPE.md)
- [CONTRACT_FINANCE_REAL_DATA_CALIBRATION.md](CONTRACT_FINANCE_REAL_DATA_CALIBRATION.md)
- [pr_intake_router_execution.md](pr_intake_router_execution.md)
- [pr_intake_router_contract_sweeper_lane.md](pr_intake_router_contract_sweeper_lane.md)
- [pr_intake_router_spiderweb_lane.md](pr_intake_router_spiderweb_lane.md)

## RLSM ontology & registry (reference)
> The FR24 / RLSM screenshot-processing pipeline migrated to
> [skywatcher-pr](https://github.com/jotaele44/skywatcher-pr) (the airspace producer).
> These reference docs remain for the operational ontology and registry contract.
- [RLSM_OPERATIONAL_ONTOLOGY_V0_1.md](RLSM_OPERATIONAL_ONTOLOGY_V0_1.md)
- [FAA_REGISTRY_PIPELINE.md](FAA_REGISTRY_PIPELINE.md)

## Spiderweb language & calibration
- [SPIDERWEB_LANGUAGE_BRIDGE.md](SPIDERWEB_LANGUAGE_BRIDGE.md)
- [SPIDERWEB_OPERATIONAL_CALIBRATION.md](SPIDERWEB_OPERATIONAL_CALIBRATION.md)
- [AIRCRAFT_HOME_BASE_INTELLIGENCE.md](AIRCRAFT_HOME_BASE_INTELLIGENCE.md)

## GIS / DEM / geodata
- [GIS_EXPORT_GUIDE.md](GIS_EXPORT_GUIDE.md) — GeoJSON/KML/QGIS consumption
- [EXTERNAL_AERODROME_LAYER.md](EXTERNAL_AERODROME_LAYER.md)
- [PR_GEODATA_INTEGRITY_AUDIT.md](PR_GEODATA_INTEGRITY_AUDIT.md)
- DEM workflow: [PR_DEM_END_TO_END_PROCESS.md](PR_DEM_END_TO_END_PROCESS.md),
  [PR_DEM_ONE_TILE_PILOT.md](PR_DEM_ONE_TILE_PILOT.md),
  [PR_DEM_REGIONAL_EXPANSION_CONTROLLER.md](PR_DEM_REGIONAL_EXPANSION_CONTROLLER.md),
  [PR_DEM_REVIEW_LOCK_WORKFLOW.md](PR_DEM_REVIEW_LOCK_WORKFLOW.md),
  [PR_DEM_FOLLOW_UP_PACKET_WORKFLOW.md](PR_DEM_FOLLOW_UP_PACKET_WORKFLOW.md),
  [PR_DEM_QGIS_QUEUE_STYLE_GUIDE.md](PR_DEM_QGIS_QUEUE_STYLE_GUIDE.md),
  [PR_DEM_QGIS_REVIEW_GUIDE.md](PR_DEM_QGIS_REVIEW_GUIDE.md)

## Dashboard & UI
- [STATIC_DASHBOARD_MODE.md](STATIC_DASHBOARD_MODE.md)

## Policy & structure
- [DATA_POLICY.md](DATA_POLICY.md)
- [MONOREPO_SPLIT_EVALUATION.md](MONOREPO_SPLIT_EVALUATION.md) — split decision (T12-97)
- [API_REFERENCE.md](API_REFERENCE.md) — generating the API reference (T12-99)

## Per-subsystem package READMEs
- [gebco/README.md](../gebco/README.md) — bathymetry / DEM
- [earthgpt/README.md](../earthgpt/README.md) — satellite metrics + selftest
- [llm/README.md](../llm/README.md) — LLM query layer
