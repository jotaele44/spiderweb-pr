/**
 * Zod runtime validation schemas for PRIIS API responses.
 * Mirrors priis.ts types; validates data at the API boundary.
 */
import { z } from "zod";

export const EvidenceTierSchema = z.enum(["T1", "T2", "T3", "T4"]);
export const ConfidenceSchema = z.union([z.literal(1), z.literal(2), z.literal(3)]);

export const AgencySchema = z.object({
  id: z.string(),
  code: z.string(),
  name: z.string(),
});

export const VendorSchema = z.object({
  id: z.string(),
  name: z.string(),
  risk: z.number(),
  tier: EvidenceTierSchema,
});

export const SiteSchema = z.object({
  id: z.string(),
  name: z.string(),
  kind: z.string(),
  lat: z.number(),
  lng: z.number(),
  sensitive: z.boolean().optional(),
  infrastructure_class: z.string().nullish().transform((v) => v ?? undefined),
  // Three TIGER GEOIDs joined by server/ingestion/ingest_tiger_pr.py. The
  // backend's /sites SELECT pulls all three; null is the legitimate
  // "no overlap" sentinel (especially for ZCTAs over uninhabited parcels).
  municipio_geoid: z.string().nullish().transform((v) => v ?? undefined),
  tract_geoid:     z.string().nullish().transform((v) => v ?? undefined),
  zcta_geoid:      z.string().nullish().transform((v) => v ?? undefined),
});

export const ContractSchema = z.object({
  id: z.string(),
  agency: z.string(),
  vendor: z.string(),
  site: z.string().nullish().transform((v) => v ?? ""),
  amount: z.number(),
  signed: z.string(),
  status: z.enum(["planned", "executed", "amended", "flagged", "closed", "unknown"]),
  tier: EvidenceTierSchema,
  note: z.string().nullish().transform((v) => v ?? undefined),
  procurement_method: z
    .enum(["competitive", "sole_source", "emergency", "amendment", "unknown"])
    .nullish()
    .transform((v) => v ?? undefined),
});

export const EventRecordSchema = z.object({
  id: z.string(),
  kind: z.enum(["contract", "imagery", "report", "outage", "permit", "field", "filing", "sighting", "other"]),
  at: z.string(),
  siteId: z.string().nullish().transform((v) => v ?? ""),
  refId: z.string().nullish().transform((v) => v ?? undefined),
  label: z.string(),
  tier: EvidenceTierSchema.optional(),
});

export const AnomalyFactorSchema = z.object({
  tag: z.enum(["finance", "spatial", "temporal", "infra", "report", "imagery", "source"]),
  note: z.string(),
});

export const AnomalySchema = z.object({
  id: z.string(),
  title: z.string(),
  category: z.enum([
    "financial", "spatial", "temporal", "infrastructure",
    "imagery", "report", "cross-domain",
  ]),
  score: z.number(),
  band: z.enum(["lo", "md", "hi"]),
  siteId: z.string().nullish().transform((v) => v ?? ""),
  summary: z.string(),
  factors: z.array(AnomalyFactorSchema).default([]),
  contracts: z.array(z.string()).default([]),
  events: z.array(z.string()).default([]),
  confidence: ConfidenceSchema,
  contradictions: z.array(z.string()).default([]),
});

export const SourceRecordSchema = z.object({
  id: z.string(),
  name: z.string(),
  tier: EvidenceTierSchema,
  kind: z.enum(["technical", "operational", "eyewitness", "secondary", "derived"]),
  status: z.enum(["online", "partial", "offline"]),
});

export const InvestigationSchema = z.object({
  id: z.string(),
  title: z.string(),
  active_vector: z.string(),
  status: z.enum(["active", "paused", "closed", "needs_review"]),
});

export const AlertRecordSchema = z.object({
  id: z.string(),
  at: z.string(),
  kind: z.enum(["finance", "spatial", "source", "anomaly", "report"]),
  title: z.string(),
  tier: EvidenceTierSchema,
  investigation: z.string().nullish().transform((v) => v ?? undefined),
});

/** Validate and coerce an API response array, silently dropping invalid rows. */
export function parseArray<T>(schema: z.ZodType<T>, raw: unknown[]): T[] {
  return raw.flatMap((item) => {
    const result = schema.safeParse(item);
    if (result.success) return [result.data];
    if (import.meta.env.DEV) console.warn("PRIIS schema mismatch", result.error.issues, item);
    return [];
  });
}
