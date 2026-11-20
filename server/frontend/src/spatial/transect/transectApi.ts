import { z } from "zod";
import { accessPointsBaseUrl, getValidated } from "../accessPoints/accessPointsApi";

const sampleSchema = z.object({
  distance_m: z.number().nonnegative(),
  xy: z.tuple([z.number(), z.number()]),
  elevation_m: z.number().nullable(),
  uncertainty_m: z.number().nonnegative().nullable(),
  interpolated: z.boolean().nullable(),
});

const profileSchema = z.object({
  source_id: z.string().nullable(),
  kind: z.string(),
  datum: z.string().min(1),
  covered_fraction: z.number().min(0).max(1),
  samples: z.array(sampleSchema),
});

const joinSchema = z.object({
  state: z.enum(["SAME_REFERENCE", "TRANSFORMED", "SEPARATE_SURFACES_ONLY", "BLOCKED_UNKNOWN_DATUM"]),
  common_datum: z.string().nullable(),
  authority: z.string().nullable(),
  reason: z.string(),
  may_difference: z.boolean(),
});

export const crossSectionSchema = z
  .looseObject({
    schema: z.literal("access_point_cross_section/1.0"),
    truth_kind: z.string().min(1),
    crs: z.string().min(1),
    spacing_m: z.number().positive(),
    length_m: z.number().positive(),
    is_continuous: z.boolean(),
    gaps: z.array(z.object({ start_m: z.number(), end_m: z.number(), length_m: z.number().nonnegative() })),
    profiles: z.array(profileSchema).min(1),
    join: joinSchema.nullable(),
    common_datum: z.string().nullable(),
    common_profiles: z.array(profileSchema),
    statement: z.string().optional(),
  })
  // A section may be drawn on one shared axis only when the join allows it.
  .refine((section) => section.common_profiles.length === 0 || section.common_datum !== null, {
    message: "common profiles without a common datum",
  })
  .refine((section) => section.is_continuous === (section.gaps.length === 0), {
    message: "is_continuous disagrees with gaps",
  });

export type CrossSection = z.infer<typeof crossSectionSchema>;
export type CrossSectionProfile = z.infer<typeof profileSchema>;

export function controlCrossSectionUrl(apiBase?: string): string {
  return `${accessPointsBaseUrl(apiBase)}/controls/cross-section`;
}

export function fetchControlCrossSection(): Promise<CrossSection> {
  return getValidated(controlCrossSectionUrl(), crossSectionSchema, "Control cross-section");
}
