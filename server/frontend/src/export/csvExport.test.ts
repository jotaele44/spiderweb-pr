import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import { exportAnomaliesCsv, exportContractsCsv } from "./csvExport";
import type { PriisData } from "../types/priis";

// escapeCell and toCsv are module-private, so the escaping is only observable
// through the download path. Rather than export them purely to make them
// testable, this captures the Blob the download builds — which also covers the
// filename and the header row on the way past.
//
// The escaping is the part that matters: a mis-quoted cell produces a file that
// opens without complaint and is silently misaligned, so a vendor name lands in
// the amount column and nobody is told.

let captured: string[] = [];

beforeEach(() => {
  captured = [];
  // jsdom implements neither createObjectURL nor revokeObjectURL.
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn((blob: Blob) => {
      // Blob.text() is async and the code under test is synchronous, so read the
      // parts the Blob was constructed from instead of the Blob itself.
      captured.push(blobText(blob));
      return "blob:stub";
    }),
    revokeObjectURL: vi.fn(),
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// jsdom Blobs expose their content synchronously via an internal buffer; fall
// back to the constructor parts recorded by the stub below if that changes.
const blobParts = new WeakMap<Blob, string>();
const RealBlob = globalThis.Blob;
class RecordingBlob extends RealBlob {
  constructor(parts: BlobPart[], options?: BlobPropertyBag) {
    super(parts, options);
    blobParts.set(this, parts.map(String).join(""));
  }
}
globalThis.Blob = RecordingBlob as unknown as typeof Blob;

function blobText(blob: Blob): string {
  return blobParts.get(blob) ?? "";
}

const csv = () => captured[0];
const dataRows = () => csv().split("\n").slice(1);

const contract = (
  over: Partial<PriisData["contracts"][number]> = {},
): PriisData["contracts"][number] => ({
  id: "C-1",
  agency: "A-1",
  vendor: "Vendor",
  site: "S-1",
  amount: 1_000_000,
  signed: "2026-01-02",
  status: "executed",
  tier: "T2",
  ...over,
});

const withContracts = (contracts: PriisData["contracts"]) =>
  ({ contracts }) as PriisData;

describe("exportContractsCsv — escaping", () => {
  it("quotes a value containing a comma", () => {
    exportContractsCsv(withContracts([contract({ vendor: "Acme, Inc." })]));

    expect(dataRows()[0]).toContain('"Acme, Inc."');
  });

  it("quotes a value containing a newline", () => {
    exportContractsCsv(withContracts([contract({ note: "line one\nline two" })]));

    expect(csv()).toContain('"line one\nline two"');
  });

  it("doubles an embedded quote", () => {
    // RFC 4180: the escape for " inside a quoted field is "". Emitting a single
    // quote terminates the field early and shifts every column after it.
    exportContractsCsv(withContracts([contract({ vendor: 'The "Main" Group' })]));

    expect(dataRows()[0]).toContain('"The ""Main"" Group"');
  });

  it("handles a value needing every escape at once", () => {
    exportContractsCsv(withContracts([contract({ note: 'a,b"c\nd' })]));

    expect(csv()).toContain('"a,b""c\nd"');
  });

  it("leaves ordinary values unquoted", () => {
    exportContractsCsv(withContracts([contract({ vendor: "Vendor" })]));

    expect(dataRows()[0]).toContain(",Vendor,");
  });

  it("renders a null site as a genuinely empty cell", () => {
    // Column count alone is not enough: String(null) is "null", which keeps the
    // row ten cells wide while writing the word "null" into a column an analyst
    // reads as a site identifier. So assert the cell's content.
    //
    // Note what this can and cannot attribute. Two layers handle the null
    // independently — `c.site ?? ""` in the row builder, and `value == null` in
    // escapeCell — and either alone is sufficient. Removing just one is
    // invisible here; removing both fails this test. That is a property of the
    // code, not a gap in the test: the contract asserted is "a null site
    // produces an empty cell", which holds while either layer stands. No
    // assertion here claims to pin a specific one.
    exportContractsCsv(withContracts([contract({ site: null as unknown as string })]));

    const cells = dataRows()[0].split(",");
    expect(cells).toHaveLength(10);
    expect(cells[4]).toBe("");
    expect(csv()).not.toContain("null");
    expect(csv()).not.toContain("undefined");
  });

  it("renders an absent optional field as empty rather than the word undefined", () => {
    exportContractsCsv(withContracts([contract({ note: undefined, procurement_method: undefined })]));

    const cells = dataRows()[0].split(",");
    expect(cells[8]).toBe("");
    expect(cells[9]).toBe("");
  });

  it("keeps a zero amount as 0 rather than blanking it", () => {
    // `value == null ? "" : String(value)` — a zero-dollar contract is a fact,
    // and an empty cell would read as missing data.
    exportContractsCsv(withContracts([contract({ amount: 0 })]));

    expect(dataRows()[0]).toContain(",0,");
  });
});

describe("exportContractsCsv — shape", () => {
  it("writes the header row first", () => {
    exportContractsCsv(withContracts([contract()]));

    expect(csv().split("\n")[0]).toBe(
      "id,signed,agency,vendor,site,amount,status,tier,note,procurement_method",
    );
  });

  it("writes one row per contract", () => {
    exportContractsCsv(
      withContracts([contract({ id: "C-1" }), contract({ id: "C-2" }), contract({ id: "C-3" })]),
    );

    expect(dataRows()).toHaveLength(3);
  });

  it("writes a header-only file for an empty dataset", () => {
    exportContractsCsv(withContracts([]));

    expect(csv().split("\n")).toHaveLength(1);
  });

  it("names the file with a date stamp", () => {
    const anchor = document.createElement("a");
    const spy = vi.spyOn(document, "createElement").mockReturnValue(anchor);

    exportContractsCsv(withContracts([contract()]));

    expect(anchor.download).toMatch(/^priis-contracts-\d{4}-\d{2}-\d{2}\.csv$/);
    spy.mockRestore();
  });
});

describe("exportAnomaliesCsv", () => {
  const anomaly = (over: Record<string, unknown> = {}) =>
    ({
      id: "A-1",
      title: "Convergence",
      category: "cross-domain",
      score: 88,
      band: "hi",
      siteId: "S-1",
      confidence: 2,
      ...over,
    }) as unknown as PriisData["anomalies"][number];

  it("writes its own header, not the contract one", () => {
    exportAnomaliesCsv({ anomalies: [anomaly()] } as PriisData);

    expect(csv().split("\n")[0]).toBe("id,title,category,score,band,siteId,confidence");
  });

  it("escapes a title containing a comma", () => {
    exportAnomaliesCsv({ anomalies: [anomaly({ title: "Vieques, phase two" })] } as PriisData);

    expect(dataRows()[0]).toContain('"Vieques, phase two"');
  });

  it("renders a null siteId as an empty cell", () => {
    exportAnomaliesCsv({ anomalies: [anomaly({ siteId: null })] } as PriisData);

    expect(dataRows()[0].split(",")).toHaveLength(7);
  });
});
