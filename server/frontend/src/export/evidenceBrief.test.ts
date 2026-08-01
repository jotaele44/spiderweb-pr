import { describe, it, expect } from "vitest";

import { buildEvidenceBrief } from "./evidenceBrief";
import type { PriisData } from "../types/priis";

// The brief is the artefact an analyst hands to someone else, so its failure
// mode is not a crash — it is a document that reads as authoritative while
// omitting or misstating something. The tests below target the parts that could
// be wrong without looking wrong: the contract total, the confidence label, and
// whether contradictions make it into the output at all.

const data = (): PriisData =>
  ({
    anomalies: [
      {
        id: "A-021",
        title: "Vieques procurement convergence",
        category: "cross-domain",
        score: 88,
        band: "hi",
        siteId: "S-1",
        summary: "Three amendments inside sixty days.",
        factors: [{ tag: "finance", note: "Sole-source amendments" }],
        contracts: ["C-1", "C-2"],
        events: ["E-1"],
        confidence: 2,
        contradictions: [],
      },
    ],
    sites: [{ id: "S-1", name: "Vieques Port", kind: "port", lat: 18.1, lng: -65.4 }],
    contracts: [
      {
        id: "C-1", agency: "A-1", vendor: "Acme", site: "S-1", amount: 1_200_000,
        signed: "2026-01-02", status: "amended", tier: "T2", procurement_method: "sole_source",
      },
      {
        id: "C-2", agency: "A-1", vendor: "Beta", site: "S-1", amount: 800_000,
        signed: "2026-02-02", status: "executed", tier: "T2",
      },
      {
        id: "C-99", agency: "A-9", vendor: "Unrelated", site: "S-9", amount: 50_000_000,
        signed: "2026-03-02", status: "executed", tier: "T3",
      },
    ],
    events: [
      { id: "E-1", kind: "contract", at: "2026-01-02", siteId: "S-1", label: "Award", tier: "T1" },
      { id: "E-9", kind: "imagery", at: "2026-04-02", siteId: "S-9", label: "Unrelated", tier: "T4" },
    ],
  }) as unknown as PriisData;

describe("buildEvidenceBrief", () => {
  it("names the anomaly and its site", () => {
    const brief = buildEvidenceBrief("A-021", data());

    expect(brief).toContain("A-021");
    expect(brief).toContain("Vieques procurement convergence");
    expect(brief).toContain("Vieques Port");
  });

  it("totals only the contracts linked to this anomaly", () => {
    // The number most likely to be read as fact and quoted onward. C-99 is worth
    // $50M and belongs to a different site — if the filter broke, the brief
    // would assert a total 25x too large with no other symptom.
    const brief = buildEvidenceBrief("A-021", data());

    expect(brief).toContain("$2,000,000");
    expect(brief).not.toContain("$50,000,000");
  });

  it("lists only the linked contracts and events", () => {
    const brief = buildEvidenceBrief("A-021", data());

    expect(brief).toContain("C-1");
    expect(brief).toContain("C-2");
    expect(brief).not.toContain("C-99");
    expect(brief).toContain("E-1");
    expect(brief).not.toContain("E-9");
  });

  it("translates the numeric confidence into a word", () => {
    // The lookup is a sparse array indexed from 1, so an off-by-one produces
    // "High" for a medium-confidence finding — a confident-sounding overstatement.
    const d = data();
    expect(buildEvidenceBrief("A-021", d)).toContain("**Confidence:** Medium");

    d.anomalies[0].confidence = 3;
    expect(buildEvidenceBrief("A-021", d)).toContain("**Confidence:** High");

    d.anomalies[0].confidence = 1;
    expect(buildEvidenceBrief("A-021", d)).toContain("**Confidence:** Low");
  });

  it("includes contradictions when there are any", () => {
    // The section a reader most needs and the one most survivable to omit —
    // a brief with no Contradictions heading reads as a finding with none.
    const d = data();
    d.anomalies[0].contradictions = ["Site coordinates disagree with the permit."];

    const brief = buildEvidenceBrief("A-021", d);

    expect(brief).toContain("## Contradictions");
    expect(brief).toContain("Site coordinates disagree with the permit.");
  });

  it("omits the contradictions heading when there are none", () => {
    expect(buildEvidenceBrief("A-021", data())).not.toContain("## Contradictions");
  });

  it("always carries the required next steps", () => {
    // These are what keep the brief a lead rather than a conclusion.
    const brief = buildEvidenceBrief("A-021", data());

    expect(brief).toContain("## Required Next Steps");
    expect(brief).toContain("Resolve any open contradictions before raising confidence.");
  });

  it("marks the document as unclassified demo output", () => {
    expect(buildEvidenceBrief("A-021", data())).toContain("UNCLASSIFIED · DEMO");
  });

  it("returns a brief saying so when the anomaly does not exist", () => {
    // Not an empty string and not a throw — the caller downloads whatever comes
    // back, so a silent empty file would look like a successful export.
    const brief = buildEvidenceBrief("A-nope", data());

    expect(brief).toContain("not found");
    expect(brief).toContain("A-nope");
  });

  it("falls back to the site id when the site is unknown", () => {
    const d = data();
    d.sites = [];

    expect(buildEvidenceBrief("A-021", d)).toContain("S-1");
  });

  it("renders an em dash for a contract with no procurement method", () => {
    // C-2 has none. Printing "undefined" in a handed-off document is the kind of
    // detail that undermines everything around it.
    const brief = buildEvidenceBrief("A-021", data());

    expect(brief).not.toContain("undefined");
    expect(brief).toContain("| — |");
  });

  it("handles an anomaly with no contracts or events without producing NaN", () => {
    const d = data();
    d.anomalies[0].contracts = [];
    d.anomalies[0].events = [];

    const brief = buildEvidenceBrief("A-021", d);

    expect(brief).toContain("$0");
    expect(brief).not.toContain("NaN");
  });
});
