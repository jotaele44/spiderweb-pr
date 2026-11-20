import type {
  AccessPointEvidence,
  AccessPointFeature,
  AccessPointRelationships,
  AccessPointSourceCoverage,
} from "./accessPointsApi";
import type { CrossSection } from "../transect/transectApi";

// Synthetic records for tests. Identifiers and values are artificial.

const tiers = {
  EXISTENCE: "CANDIDATE",
  MORPHOLOGY: "UNRESOLVED",
  NATURAL_OR_ARTIFICIAL_ORIGIN: "UNRESOLVED",
  PHYSICAL_OPENING: "UNRESOLVED",
  ACCESSIBILITY: "UNRESOLVED",
  FUNCTION: "UNRESOLVED",
  CONNECTIVITY: "UNRESOLVED",
  TEMPORAL_VALIDITY: "UNRESOLVED",
} as const;

export const provenance = { path: "registry/access_points/offshore.json", sha256: "ab".repeat(32), exists: true, row_count: 3 };
export const scope = { identity_effect: "NONE" as const, identity_default: "CANDIDATE_NOT_IDENTITY", state: "PROVISIONAL", note: "candidates" };

export function feature(overrides: {
  id: string;
  status?: AccessPointFeature["properties"]["status"];
  coordinates?: [number, number] | null;
  uncertainty?: number | null;
  rung?: AccessPointFeature["properties"]["assertion_rung"];
  labels?: string[];
}): AccessPointFeature {
  const status = overrides.status ?? "CANDIDATE";
  const coordinates = overrides.coordinates === undefined ? ([-66.1, 17.95] as [number, number]) : overrides.coordinates;
  const uncertainty = overrides.uncertainty ?? null;
  return {
    type: "Feature",
    id: overrides.id,
    geometry: coordinates === null ? null : { type: "Point", coordinates },
    properties: {
      feature_id: overrides.id,
      registry: "access_point.offshore",
      registry_code: "OFAP",
      feature_class: "UNCLASSIFIED_ANOMALY",
      status,
      is_verified: status === "VERIFIED",
      assertion_rung: overrides.rung ?? "ANOMALY",
      dimensions: { ...tiers },
      has_geometry: coordinates !== null,
      geometry_basis: coordinates === null ? "LOCALITY_LABEL_ONLY" : "MEASURED",
      geometry_is_modeled: false,
      horizontal_uncertainty_m: uncertainty,
      horizontal_uncertainty_state: uncertainty === null ? "UNKNOWN" : "STATED",
      locality_labels: coordinates === null ? ["Synthetic locality"] : [],
      provisional_labels: overrides.labels ?? [],
      raw_names: [],
      observation_count: 1,
      created_utc: "2026-11-15T00:00:00Z",
      updated_utc: null,
      notes: null,
    },
  };
}

export const seed = feature({ id: "OFAP-PR-000001", status: "PROVISIONAL_DISCOVERY", coordinates: null, labels: ["OSAP-SEED-001"] });
export const candidate = feature({ id: "OFAP-PR-000006", uncertainty: 25 });
export const verified = feature({ id: "OFAP-PR-000007", status: "VERIFIED", rung: "OPENING", coordinates: [-66.2, 18.0] });
export const rejected = feature({ id: "OFAP-PR-000008", status: "REJECTED" });

export const evidence: AccessPointEvidence = {
  feature_id: "OFAP-PR-000006",
  status: "CANDIDATE",
  assertion_rung: "FEATURE",
  promotion_blockers: ["evidence reaches FEATURE; a verified access point needs a directly observed physical opening"],
  assertions: [
    {
      dimension: "PHYSICAL_OPENING",
      asserted_tier: "DIRECT",
      effective_tier: "CANDIDATE",
      claim_class: "COMPUTED",
      basis: ["bathymetric_anomaly"],
      statement: "steep round basin",
      method: "closed-basin-delineation",
      method_version: "1",
      adjudication: "UNREVIEWED",
      adjudicated_by: null,
      source_ids: ["APSRC-0000000000000001"],
      connectivity_kind: null,
      valid_from: null,
      valid_to: null,
    },
    {
      dimension: "EXISTENCE",
      asserted_tier: "SUPPORTING",
      effective_tier: "SUPPORTING",
      claim_class: "COMPUTED",
      basis: ["bathymetric_anomaly"],
      statement: "closed basin 12 m deep",
      method: "closed-basin-delineation",
      method_version: "1",
      adjudication: "UNREVIEWED",
      adjudicated_by: null,
      source_ids: ["APSRC-0000000000000001"],
      connectivity_kind: null,
      valid_from: null,
      valid_to: null,
    },
  ],
  observations: [{ observation_id: "OFAP-OBS-0000000000000001" }],
  sources: [
    {
      source_id: "APSRC-0000000000000001",
      provider: "TEST_PROVIDER",
      title: "synthetic survey",
      manifestation_sha256: "cd".repeat(32),
      retrieved_utc: "2026-11-15T00:00:00Z",
      published_date: "2025-06-01",
      survey_date: null,
      provenance_state: "REGISTERED",
    },
  ],
  provenance,
  scope,
};

export const coverage: AccessPointSourceCoverage = {
  sources: [
    { source_id: "APSRC-0000000000000002", provider: "TEST_INVENTORY", title: "synthetic row", provenance_state: "REFERENCED_ONLY", is_direct_measurement: false, features_citing: 0 },
  ],
  by_provider: { TEST_INVENTORY: { REFERENCED_ONLY: 1 } },
  direct_measurement_sources: 0,
  note: "a listed source is a reference",
  provenance,
  scope,
};

export function relationships(classes: AccessPointRelationships["relationships"][number]["render_class"][]): AccessPointRelationships {
  return {
    relationships: classes.map((renderClass, index) => ({
      relationship_id: `APREL-${String(index).padStart(16, "0")}`,
      relationship_type: renderClass === "verified" ? "MEASURED_HYDRAULIC_CONNECTION" : "HYPOTHESIZED_CONNECTION",
      source: { namespace: "access_point.inland", identifier: `INAP-PR-00000${index + 1}` },
      target: { namespace: "access_point.offshore", identifier: `OFAP-PR-00000${index + 1}` },
      render_class: renderClass,
      is_verified: renderClass === "verified",
      connectivity_kind: "HYDRAULIC_CONNECTION",
      asserted_tier: "DIRECT",
      effective_tier: renderClass === "verified" ? "DIRECT" : "CANDIDATE",
      claim_class: "HYPOTHESIS",
      basis: ["synthetic"],
      statement: `synthetic ${renderClass} link`,
      distance_m: null,
      adjudication: "UNREVIEWED",
    })),
    number_returned: classes.length,
    render_classes: ["verified", "context", "hypothesized", "contradicted", "unresolved"],
    provenance: { ...provenance, path: "registry/access_points/relationships.json" },
    scope,
  };
}

const sample = (distance: number, elevation: number | null, sigma: number | null = 0.2) => ({
  distance_m: distance,
  xy: [distance, 0] as [number, number],
  elevation_m: elevation,
  uncertainty_m: elevation === null ? null : sigma,
  interpolated: elevation === null ? null : false,
});

export function crossSection(joined: boolean): CrossSection {
  const sea = { source_id: null, kind: "BATHYMETRY", datum: joined ? "PRVD02" : "MLLW", covered_fraction: 0.4, samples: [sample(0, -8), sample(10, -6), sample(20, null), sample(30, null), sample(40, null)] };
  const land = { source_id: null, kind: "TERRAIN_BARE_EARTH", datum: "PRVD02", covered_fraction: 0.4, samples: [sample(0, null), sample(10, null), sample(20, null), sample(30, 1), sample(40, 3)] };
  return {
    schema: "access_point_cross_section/1.0",
    truth_kind: "SYNTHETIC_CONTROL",
    crs: "EPSG:32620",
    spacing_m: 10,
    length_m: 40,
    is_continuous: false,
    gaps: [{ start_m: 20, end_m: 20, length_m: 0 }],
    profiles: [land, sea],
    join: joined
      ? { state: "TRANSFORMED", common_datum: "PRVD02", authority: "synthetic test authority", reason: "seabed values moved to PRVD02", may_difference: true }
      : { state: "SEPARATE_SURFACES_ONLY", common_datum: null, authority: null, reason: "no certified transform between MLLW and PRVD02", may_difference: false },
    common_datum: joined ? "PRVD02" : null,
    common_profiles: joined ? [land, sea] : [],
    statement: "synthetic control surfaces",
  };
}
