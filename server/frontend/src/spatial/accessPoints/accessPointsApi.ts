import { z } from "zod";
import { fetchWithTimeout } from "../../api/client";
import { API_BASE } from "../../config";

/**
 * Client for the backend's access-point registry routes (`/v1/access-points`).
 *
 * There are two registries, Inland Access Points and Off-Shore Access Points,
 * and they are independent: each has its own endpoint, its own fetcher and its
 * own failure. Nothing here merges them.
 *
 * Every response is validated at this boundary. A payload that does not match
 * the contract is an error the caller must surface; it is never coerced into
 * an empty list, because "no records" and "an unreadable answer" are different
 * statements about the registry.
 */

export const ACCESS_POINT_REGISTRIES = ["inland", "offshore"] as const;
export type AccessPointRegistryId = (typeof ACCESS_POINT_REGISTRIES)[number];

export const REGISTRY_TITLES: Record<AccessPointRegistryId, string> = {
  inland: "Inland Access Points",
  offshore: "Off-Shore Access Points",
};

export const REGISTRY_STATUSES = [
  "PROVISIONAL_DISCOVERY",
  "CANDIDATE",
  "UNDER_REVIEW",
  "VERIFIED",
  "REJECTED",
  "SUPERSEDED",
] as const;
export type RegistryStatus = (typeof REGISTRY_STATUSES)[number];

/** Weakest to strongest. Each rung requires the one below it. */
export const ASSERTION_RUNGS = ["ANOMALY", "FEATURE", "OPENING", "PASSAGE", "CONNECTION"] as const;
export type AssertionRung = (typeof ASSERTION_RUNGS)[number];

export const EVIDENCE_TIERS = ["UNRESOLVED", "CANDIDATE", "SUPPORTING", "DIRECT", "CONTRADICTED"] as const;
export type EvidenceTierName = (typeof EVIDENCE_TIERS)[number];

export const EVIDENCE_DIMENSIONS = [
  "EXISTENCE",
  "MORPHOLOGY",
  "NATURAL_OR_ARTIFICIAL_ORIGIN",
  "PHYSICAL_OPENING",
  "ACCESSIBILITY",
  "FUNCTION",
  "CONNECTIVITY",
  "TEMPORAL_VALIDITY",
] as const;
export type EvidenceDimensionName = (typeof EVIDENCE_DIMENSIONS)[number];

export const RENDER_CLASSES = ["verified", "context", "hypothesized", "contradicted", "unresolved"] as const;
export type RelationshipRenderClass = (typeof RENDER_CLASSES)[number];

/** How a status is symbolised and filtered. `retired` records are never drawn. */
export type StatusGroup = "verified" | "candidate" | "provisional" | "retired";
export const DRAWN_STATUS_GROUPS = ["verified", "candidate", "provisional"] as const;
export type DrawnStatusGroup = (typeof DRAWN_STATUS_GROUPS)[number];

export const STATUS_GROUP_MEMBERS: Record<DrawnStatusGroup, readonly RegistryStatus[]> = {
  verified: ["VERIFIED"],
  candidate: ["CANDIDATE", "UNDER_REVIEW"],
  provisional: ["PROVISIONAL_DISCOVERY"],
};

export function statusGroup(status: RegistryStatus): StatusGroup {
  if (status === "VERIFIED") return "verified";
  if (status === "CANDIDATE" || status === "UNDER_REVIEW") return "candidate";
  if (status === "PROVISIONAL_DISCOVERY") return "provisional";
  return "retired";
}

/** First 12 characters of a digest, for display next to a document path. */
/** Enum value as lower-case words for display. */
export function words(value: string): string {
  return value.toLowerCase().replace(/_/g, " ");
}

export function shortHash(sha256: string | null | undefined): string {
  return sha256 ? sha256.slice(0, 12) : "not recorded";
}

// ── Schemas ──────────────────────────────────────────────────────────────────

const tierSchema = z.enum(EVIDENCE_TIERS);
const statusSchema = z.enum(REGISTRY_STATUSES);
const rungSchema = z.enum(ASSERTION_RUNGS);
const count = z.number().int().nonnegative();

export const provenanceSchema = z.looseObject({
  path: z.string().min(1),
  sha256: z.string().min(1),
  exists: z.boolean().optional(),
  row_count: count.optional(),
});

export const scopeSchema = z.looseObject({
  identity_effect: z.literal("NONE"),
  identity_default: z.string(),
  state: z.string(),
  note: z.string(),
});

const longitude = z.number().min(-180).max(180);
const latitude = z.number().min(-90).max(90);

export const pointGeometrySchema = z.object({
  type: z.literal("Point"),
  coordinates: z.tuple([longitude, latitude], z.number()),
});

const otherGeometrySchema = z.looseObject({
  type: z.enum(["MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon", "GeometryCollection"]),
});

export const geometrySchema = z.union([pointGeometrySchema, otherGeometrySchema]);

export const dimensionsSchema = z.object({
  EXISTENCE: tierSchema,
  MORPHOLOGY: tierSchema,
  NATURAL_OR_ARTIFICIAL_ORIGIN: tierSchema,
  PHYSICAL_OPENING: tierSchema,
  ACCESSIBILITY: tierSchema,
  FUNCTION: tierSchema,
  CONNECTIVITY: tierSchema,
  TEMPORAL_VALIDITY: tierSchema,
});

export const featurePropertiesSchema = z.looseObject({
  feature_id: z.string().min(1),
  registry: z.string(),
  registry_code: z.enum(["INAP", "OFAP"]),
  feature_class: z.string(),
  status: statusSchema,
  is_verified: z.boolean(),
  assertion_rung: rungSchema,
  dimensions: dimensionsSchema,
  has_geometry: z.boolean(),
  geometry_basis: z.string(),
  geometry_is_modeled: z.boolean(),
  horizontal_uncertainty_m: z.number().nonnegative().nullable(),
  horizontal_uncertainty_state: z.enum(["STATED", "UNKNOWN"]),
  locality_labels: z.array(z.string()),
  provisional_labels: z.array(z.string()),
  raw_names: z.array(z.string()),
  observation_count: count,
  created_utc: z.string().nullable(),
  updated_utc: z.string().nullable(),
  notes: z.string().nullable(),
});

export const featureSchema = z
  .object({
    type: z.literal("Feature"),
    id: z.string().min(1),
    geometry: geometrySchema.nullable(),
    properties: featurePropertiesSchema,
  })
  // A record that claims verification its status does not carry, or geometry
  // it does not have, is a contract violation rather than something to guess at.
  .refine((feature) => feature.properties.is_verified === (feature.properties.status === "VERIFIED"), {
    message: "is_verified disagrees with status",
  })
  .refine((feature) => feature.properties.has_geometry === (feature.geometry !== null), {
    message: "has_geometry disagrees with geometry",
  });

export const featureCollectionSchema = z.object({
  type: z.literal("FeatureCollection"),
  features: z.array(featureSchema),
  number_matched: count,
  number_returned: count,
  unlocated_count: count,
  next_cursor: z.string().nullable(),
  crs: z.literal("OGC:CRS84"),
  provenance: provenanceSchema,
  scope: scopeSchema,
});

export const assertionSchema = z.looseObject({
  dimension: z.enum(EVIDENCE_DIMENSIONS),
  asserted_tier: tierSchema,
  effective_tier: tierSchema,
  claim_class: z.string(),
  basis: z.array(z.string()),
  statement: z.string(),
  method: z.string().nullable(),
  method_version: z.string().nullable(),
  adjudication: z.string(),
  adjudicated_by: z.string().nullable(),
  source_ids: z.array(z.string()),
  connectivity_kind: z.string().nullable(),
  valid_from: z.string().nullable(),
  valid_to: z.string().nullable(),
});

export const provenanceStateSchema = z.enum(["REGISTERED", "REFERENCED_ONLY", "UNREGISTERED"]);

export const evidenceSourceSchema = z.looseObject({
  source_id: z.string().min(1),
  provider: z.string(),
  title: z.string(),
  native_identifier: z.string().nullable().optional(),
  source_uri: z.string().nullable().optional(),
  manifestation_sha256: z.string().nullable().optional(),
  retrieved_utc: z.string().nullable().optional(),
  published_date: z.string().nullable().optional(),
  survey_date: z.string().nullable().optional(),
  provenance_state: provenanceStateSchema,
  product_stage: z.string().nullable().optional(),
  sensor_type: z.string().nullable().optional(),
  coverage_state: z.string().nullable().optional(),
});

export const evidenceSchema = z.object({
  feature_id: z.string().min(1),
  status: statusSchema,
  assertion_rung: rungSchema,
  promotion_blockers: z.array(z.string()),
  assertions: z.array(assertionSchema),
  observations: z.array(z.looseObject({ observation_id: z.string().min(1) })),
  sources: z.array(evidenceSourceSchema),
  provenance: provenanceSchema,
  scope: scopeSchema,
});

export const coverageSourceSchema = evidenceSourceSchema.extend({
  is_direct_measurement: z.boolean(),
  features_citing: count,
});

export const sourceCoverageSchema = z.object({
  sources: z.array(coverageSourceSchema),
  by_provider: z.record(z.string(), z.record(z.string(), count)),
  direct_measurement_sources: count,
  note: z.string(),
  provenance: provenanceSchema,
  scope: scopeSchema,
});

const typedRefSchema = z.object({ namespace: z.string().min(1), identifier: z.string().min(1) });

export const relationshipSchema = z
  .looseObject({
    relationship_id: z.string().min(1),
    relationship_type: z.string().min(1),
    source: typedRefSchema,
    target: typedRefSchema,
    render_class: z.enum(RENDER_CLASSES),
    is_verified: z.boolean(),
    connectivity_kind: z.string().nullable(),
    asserted_tier: tierSchema,
    effective_tier: tierSchema,
    claim_class: z.string(),
    basis: z.array(z.string()),
    statement: z.string(),
    distance_m: z.number().nonnegative().nullable(),
    adjudication: z.string(),
  })
  // The one combination that would let an unverified link be drawn as a
  // verified one. Refuse it here instead of trusting either field alone.
  .refine((relationship) => (relationship.render_class === "verified") === relationship.is_verified, {
    message: "render_class disagrees with is_verified",
  });

export const relationshipsSchema = z.object({
  relationships: z.array(relationshipSchema),
  number_returned: count,
  render_classes: z.array(z.string()),
  provenance: provenanceSchema,
  scope: scopeSchema,
});

export const registryIndexSchema = z.object({
  service_version: z.string(),
  registries: z.array(
    z.looseObject({
      registry: z.enum(ACCESS_POINT_REGISTRIES),
      namespace: z.string(),
      code: z.enum(["INAP", "OFAP"]),
      title: z.string(),
      available: z.boolean(),
      reason: z.string().optional(),
      provenance: provenanceSchema.optional(),
    }),
  ),
  scope: scopeSchema,
});

export const vocabularySchema = z.looseObject({
  evidence_dimensions: z.array(z.string()),
  evidence_tiers: z.array(z.string()),
  registry_statuses: z.array(z.string()),
  render_classes: z.array(z.string()),
  feature_classes: z.record(z.string(), z.array(z.string())),
});

export type AccessPointProvenance = z.infer<typeof provenanceSchema>;
export type AccessPointScope = z.infer<typeof scopeSchema>;
export type AccessPointFeature = z.infer<typeof featureSchema>;
export type AccessPointFeatureProperties = z.infer<typeof featurePropertiesSchema>;
export type AccessPointFeatureCollection = z.infer<typeof featureCollectionSchema>;
export type AccessPointAssertion = z.infer<typeof assertionSchema>;
export type AccessPointEvidenceSource = z.infer<typeof evidenceSourceSchema>;
export type AccessPointEvidence = z.infer<typeof evidenceSchema>;
export type AccessPointCoverageSource = z.infer<typeof coverageSourceSchema>;
export type AccessPointSourceCoverage = z.infer<typeof sourceCoverageSchema>;
export type AccessPointRelationship = z.infer<typeof relationshipSchema>;
export type AccessPointRelationships = z.infer<typeof relationshipsSchema>;
export type AccessPointRegistryIndex = z.infer<typeof registryIndexSchema>;
export type AccessPointVocabulary = z.infer<typeof vocabularySchema>;

// ── URLs ─────────────────────────────────────────────────────────────────────

export function accessPointsBaseUrl(apiBase: string = API_BASE): string {
  return `${apiBase.replace(/\/$/, "")}/v1/access-points`;
}

export interface FeatureQuery {
  bbox?: readonly [number, number, number, number];
  status?: RegistryStatus;
  featureClass?: string;
  limit?: number;
  cursor?: string;
}

export function featuresUrl(registry: AccessPointRegistryId, query: FeatureQuery = {}, apiBase?: string): string {
  const params = new URLSearchParams();
  if (query.bbox) params.set("bbox", query.bbox.join(","));
  if (query.status) params.set("status", query.status);
  if (query.featureClass) params.set("feature_class", query.featureClass);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.cursor) params.set("cursor", query.cursor);
  const search = params.toString();
  return `${accessPointsBaseUrl(apiBase)}/${registry}/features${search ? `?${search}` : ""}`;
}

export function evidenceUrl(registry: AccessPointRegistryId, featureId: string, apiBase?: string): string {
  return `${accessPointsBaseUrl(apiBase)}/${registry}/features/${encodeURIComponent(featureId)}/evidence`;
}

export function sourcesUrl(registry: AccessPointRegistryId, apiBase?: string): string {
  return `${accessPointsBaseUrl(apiBase)}/${registry}/sources`;
}

export function relationshipsUrl(
  query: { featureId?: string; renderClass?: RelationshipRenderClass } = {},
  apiBase?: string,
): string {
  const params = new URLSearchParams();
  if (query.featureId) params.set("feature_id", query.featureId);
  if (query.renderClass) params.set("render_class", query.renderClass);
  const search = params.toString();
  return `${accessPointsBaseUrl(apiBase)}/relationships${search ? `?${search}` : ""}`;
}

// ── Fetching ─────────────────────────────────────────────────────────────────

/** A non-2xx answer from the access-point service, with its `detail` text. */
export class AccessPointsRequestError extends Error {
  readonly status: number;
  constructor(status: number, detail: string) {
    super(`${detail} (HTTP ${status})`);
    this.name = "AccessPointsRequestError";
    this.status = status;
  }
}

/** A 2xx answer whose body does not match the contract. */
export class AccessPointsContractError extends Error {
  constructor(what: string, issues: string) {
    super(`${what} response did not match the expected contract: ${issues}`);
    this.name = "AccessPointsContractError";
  }
}

const errorBodySchema = z.object({ detail: z.string() });

export async function getValidated<T>(url: string, schema: z.ZodType<T>, what: string): Promise<T> {
  const response = await fetchWithTimeout(url);
  if (!response.ok) {
    let detail = `${what} request failed`;
    try {
      const parsed = errorBodySchema.safeParse(await response.json());
      if (parsed.success) detail = parsed.data.detail;
    } catch {
      // A non-JSON error body carries no detail; the status code still does.
    }
    throw new AccessPointsRequestError(response.status, detail);
  }
  const parsed = schema.safeParse(await response.json());
  if (!parsed.success) {
    const issues = parsed.error.issues
      .slice(0, 3)
      .map((issue) => `${issue.path.join(".") || "(root)"}: ${issue.message}`)
      .join("; ");
    throw new AccessPointsContractError(what, issues);
  }
  return parsed.data;
}

export function fetchAccessPointRegistries(): Promise<AccessPointRegistryIndex> {
  return getValidated(accessPointsBaseUrl(), registryIndexSchema, "Registry index");
}

export function fetchAccessPointVocabulary(): Promise<AccessPointVocabulary> {
  return getValidated(`${accessPointsBaseUrl()}/vocabulary`, vocabularySchema, "Vocabulary");
}

export function fetchInlandFeatures(query?: FeatureQuery): Promise<AccessPointFeatureCollection> {
  return getValidated(featuresUrl("inland", query), featureCollectionSchema, REGISTRY_TITLES.inland);
}

export function fetchOffshoreFeatures(query?: FeatureQuery): Promise<AccessPointFeatureCollection> {
  return getValidated(featuresUrl("offshore", query), featureCollectionSchema, REGISTRY_TITLES.offshore);
}

/** One fetcher per registry: separate endpoint, separate state, separate failure. */
export const FEATURE_FETCHERS: Record<
  AccessPointRegistryId,
  (query?: FeatureQuery) => Promise<AccessPointFeatureCollection>
> = {
  inland: fetchInlandFeatures,
  offshore: fetchOffshoreFeatures,
};

export const FEATURE_PAGE_LIMIT = 500;
export const FEATURE_MAX_PAGES = 20;

export interface RegistrySnapshot {
  features: AccessPointFeature[];
  numberMatched: number;
  /** True when paging stopped at the page cap with records still unread. */
  truncated: boolean;
  provenance: AccessPointProvenance;
  scope: AccessPointScope;
}

/** Follow `next_cursor` until the registry is read or the page cap is hit. */
export async function fetchRegistrySnapshot(registry: AccessPointRegistryId): Promise<RegistrySnapshot> {
  const fetchPage = FEATURE_FETCHERS[registry];
  const features: AccessPointFeature[] = [];
  let cursor: string | undefined;
  let page = await fetchPage({ limit: FEATURE_PAGE_LIMIT });
  features.push(...page.features);
  for (let pages = 1; page.next_cursor !== null && pages < FEATURE_MAX_PAGES; pages += 1) {
    cursor = page.next_cursor;
    page = await fetchPage({ limit: FEATURE_PAGE_LIMIT, cursor });
    features.push(...page.features);
  }
  return {
    features,
    numberMatched: page.number_matched,
    truncated: page.next_cursor !== null,
    provenance: page.provenance,
    scope: page.scope,
  };
}

export function fetchAccessPointEvidence(
  registry: AccessPointRegistryId,
  featureId: string,
): Promise<AccessPointEvidence> {
  return getValidated(evidenceUrl(registry, featureId), evidenceSchema, "Evidence");
}

export function fetchSourceCoverage(registry: AccessPointRegistryId): Promise<AccessPointSourceCoverage> {
  return getValidated(sourcesUrl(registry), sourceCoverageSchema, `${REGISTRY_TITLES[registry]} source coverage`);
}

export function fetchAccessPointRelationships(
  query?: { featureId?: string; renderClass?: RelationshipRenderClass },
): Promise<AccessPointRelationships> {
  return getValidated(relationshipsUrl(query), relationshipsSchema, "Relationships");
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "request failed";
}
