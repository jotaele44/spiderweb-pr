import { describe, it, expect, vi, afterEach } from "vitest";

import {
  AnomalySchema,
  ContractSchema,
  SiteSchema,
  parseArray,
} from "./priis";

// parseArray is the boundary every API response crosses, and it is the one
// function here that fails silently by design: an invalid row is dropped, not
// reported. On an oversight surface that is the dangerous direction — a
// contract that fails validation does not appear as an error, it simply is not
// in the total. These tests pin both halves: that valid data survives intact,
// and that the dropping is real and bounded rather than incidental.

afterEach(() => {
  vi.restoreAllMocks();
});

const contract = (over: Record<string, unknown> = {}) => ({
  id: "C-1",
  agency: "A-1",
  vendor: "V-1",
  site: "S-1",
  amount: 1_000_000,
  signed: "2026-01-02",
  status: "executed",
  tier: "T2",
  ...over,
});

describe("parseArray", () => {
  it("keeps every valid row, in order", () => {
    const rows = parseArray(ContractSchema, [
      contract({ id: "C-1" }),
      contract({ id: "C-2" }),
      contract({ id: "C-3" }),
    ]);

    expect(rows.map((r) => r.id)).toEqual(["C-1", "C-2", "C-3"]);
  });

  it("drops an invalid row and keeps the rest", () => {
    // The documented behaviour. Worth pinning precisely, because the failure
    // mode people care about is a silently short list.
    const rows = parseArray(ContractSchema, [
      contract({ id: "C-1" }),
      { id: "C-2" }, // missing everything else
      contract({ id: "C-3" }),
    ]);

    expect(rows.map((r) => r.id)).toEqual(["C-1", "C-3"]);
  });

  it("drops a row whose status is outside the enum", () => {
    // A backend that starts emitting a new status makes those contracts vanish
    // from the UI rather than rendering as unknown. That is a real consequence
    // of a closed enum plus silent dropping, and it should be a deliberate
    // choice rather than a surprise.
    const rows = parseArray(ContractSchema, [contract({ status: "cancelled" })]);

    expect(rows).toHaveLength(0);
  });

  it("drops a row whose amount is a string, rather than coercing it", () => {
    // Zod does not coerce here. "1000000" would otherwise become a real dollar
    // figure that no one entered.
    expect(parseArray(ContractSchema, [contract({ amount: "1000000" })])).toHaveLength(0);
  });

  it("returns an empty array for an all-invalid payload rather than throwing", () => {
    expect(parseArray(ContractSchema, [{}, null, 42, "nonsense"])).toEqual([]);
  });

  it("returns an empty array for an empty payload", () => {
    expect(parseArray(ContractSchema, [])).toEqual([]);
  });

  it("warns in dev when it drops a row, so the loss is at least observable", () => {
    // The only signal that anything was dropped. If this disappeared, a schema
    // drift would be completely invisible in development too.
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);

    parseArray(ContractSchema, [{ id: "bad" }]);

    expect(warn).toHaveBeenCalled();
  });

  it("does not warn when everything parses", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);

    parseArray(ContractSchema, [contract()]);

    expect(warn).not.toHaveBeenCalled();
  });
});

describe("null coercion at the boundary", () => {
  // The backend returns SQL NULLs for genuinely absent values. These transforms
  // are what stop "null" reaching the UI as a string or an undefined render.

  it("turns a null contract site into an empty string, not a dropped row", () => {
    const [c] = parseArray(ContractSchema, [contract({ site: null })]);

    expect(c.site).toBe("");
  });

  it("turns a null note and procurement method into undefined", () => {
    const [c] = parseArray(ContractSchema, [contract({ note: null, procurement_method: null })]);

    expect(c.note).toBeUndefined();
    expect(c.procurement_method).toBeUndefined();
  });

  it("accepts a site whose TIGER geoids are all null", () => {
    // null is the legitimate "no overlap" sentinel — especially for ZCTAs over
    // uninhabited parcels — so these rows must survive, not be dropped.
    const [s] = parseArray(SiteSchema, [
      {
        id: "S-1",
        name: "Site",
        kind: "port",
        lat: 18.2,
        lng: -66.5,
        municipio_geoid: null,
        tract_geoid: null,
        zcta_geoid: null,
      },
    ]);

    expect(s).toBeDefined();
    expect(s.municipio_geoid).toBeUndefined();
  });

  it("keeps a site whose coordinates are zero", () => {
    // 0 is a valid latitude and longitude. A truthiness check anywhere in this
    // chain would drop such a row.
    const [s] = parseArray(SiteSchema, [
      { id: "S-0", name: "Null Island", kind: "buoy", lat: 0, lng: 0 },
    ]);

    expect(s).toBeDefined();
    expect(s.lat).toBe(0);
  });
});

describe("AnomalySchema defaults", () => {
  const anomaly = (over: Record<string, unknown> = {}) => ({
    id: "A-1",
    title: "Convergence",
    category: "cross-domain",
    score: 88,
    band: "hi",
    summary: "…",
    confidence: 2,
    ...over,
  });

  it("defaults the list fields to empty arrays rather than undefined", () => {
    // Downstream code calls .includes() and .length on these without guarding,
    // so a missing field must arrive as [] or the module throws at render.
    const [a] = parseArray(AnomalySchema, [anomaly()]);

    expect(a.factors).toEqual([]);
    expect(a.contracts).toEqual([]);
    expect(a.events).toEqual([]);
    expect(a.contradictions).toEqual([]);
  });

  it("accepts only the three confidence levels", () => {
    expect(parseArray(AnomalySchema, [anomaly({ confidence: 3 })])).toHaveLength(1);
    expect(parseArray(AnomalySchema, [anomaly({ confidence: 0 })])).toHaveLength(0);
    expect(parseArray(AnomalySchema, [anomaly({ confidence: 4 })])).toHaveLength(0);
  });

  it("accepts only the three bands", () => {
    expect(parseArray(AnomalySchema, [anomaly({ band: "hi" })])).toHaveLength(1);
    expect(parseArray(AnomalySchema, [anomaly({ band: "high" })])).toHaveLength(0);
  });
});
