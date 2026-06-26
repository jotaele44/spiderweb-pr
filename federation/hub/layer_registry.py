"""SpiderWeb federation layer registry.

The registry records downstream consumer layers that can be activated from
validated producer packages. Entries are deliberately declarative so external
producer repos remain decoupled from SpiderWeb internals.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class LayerRegistryEntry:
    """Declarative metadata for a SpiderWeb evidence/feature layer."""

    layer_id: str
    producer: str
    export_contract_version: str
    adapter_module: str
    engine_module: str
    input_artifacts: tuple[str, ...]
    output_artifacts: tuple[str, ...]
    score_features: tuple[str, ...]
    manifest_gate_module: str = ""
    manifest_gate_argument: str = ""
    manifest_artifact: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CONTRACT_FINANCE_LAYER = LayerRegistryEntry(
    layer_id="contract_finance",
    producer="moneysweep-pr",
    export_contract_version="1.2.0",
    adapter_module="federation.hub.adapters.moneysweep",
    engine_module="readiness.contract_finance_layer",
    manifest_gate_module="readiness.contract_finance_manifest_gate",
    manifest_gate_argument="--artifact-manifest",
    manifest_artifact="artifact_manifest.json",
    input_artifacts=(
        "artifact_manifest.json",
        "contract_awards.geojson",
        "financial_flows.geojson",
        "municipality_funding_density.csv",
        "entity_graph.graphml",
        "contract_finance_ingest_report.json",
    ),
    output_artifacts=(
        "contract_finance_scored_overlay.geojson",
        "contract_finance_layer_report.json",
    ),
    score_features=(
        "entity_convergence",
        "municipal_density",
        "temporal_funding_pulse",
    ),
)


SPIDERWEB_SPATIAL_LANE = LayerRegistryEntry(
    layer_id="spiderweb_spatial_lane",
    producer="pr-intake-router",
    export_contract_version="0.1.0",
    adapter_module="",  # external: moneysweep-pr shared.pr_intake_router writes the CSV directly
    engine_module="readiness.spiderweb_spatial_lane",
    input_artifacts=(
        "spiderweb_pr_derivatives.csv",
    ),
    output_artifacts=(
        "data/normalized/spatial_intake_items.csv",
        "data/normalized/infrastructure_assets.csv",
        "data/normalized/aviation_activity_items.csv",
        "data/normalized/maritime_activity_items.csv",
        "data/normalized/hydro_environment_items.csv",
        "data/normalized/science_dataset_items.csv",
        "data/exports/poi_candidates.geojson",
        "data/exports/aoi_candidates.geojson",
        "data/exports/corridor_candidates.geojson",
        "spiderweb_spatial_lane_report.json",
    ),
    score_features=(),
)


LAYER_REGISTRY: dict[str, LayerRegistryEntry] = {
    CONTRACT_FINANCE_LAYER.layer_id: CONTRACT_FINANCE_LAYER,
    SPIDERWEB_SPATIAL_LANE.layer_id: SPIDERWEB_SPATIAL_LANE,
}


def get_layer_entry(layer_id: str) -> LayerRegistryEntry:
    """Return a registered layer entry or raise KeyError."""

    return LAYER_REGISTRY[layer_id]
