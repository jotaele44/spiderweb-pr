import { describe, it, expect, vi, afterEach } from "vitest";

import { fetchPriisData, fetchPriisDataWithFallback } from "./client";

// The behaviour worth protecting here is the fallback. When the backend is
// unreachable, fetchPriisDataWithFallback returns the bundled demo dataset and
// reports `live: false` — the flag is the *only* thing distinguishing an
// investigation built on real records from one built on mock data. Everything
// else about the two return values looks identical to a caller.

const okJson = (body: unknown) =>
  ({ ok: true, status: 200, json: () => Promise.resolve(body) }) as unknown as Response;

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

const anomaly = (over: Record<string, unknown> = {}) => ({
  id: "A-1",
  title: "Convergence",
  category: "cross-domain",
  score: 88,
  band: "lo",
  summary: "…",
  confidence: 2,
  ...over,
});

/** Route each endpoint to a canned payload; anything unlisted returns []. */
function stubEndpoints(byPath: Record<string, unknown[]>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const path = url.slice(url.lastIndexOf("/"));
      return Promise.resolve(okJson(byPath[path] ?? []));
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("fetchPriisDataWithFallback", () => {
  it("reports live data as live", async () => {
    stubEndpoints({ "/contracts": [contract()] });

    const { data, live } = await fetchPriisDataWithFallback();

    expect(live).toBe(true);
    expect(data.contracts).toHaveLength(1);
  });

  it("falls back to the bundled mock when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("ECONNREFUSED"))));

    const { data, live } = await fetchPriisDataWithFallback();

    expect(live).toBe(false);
    expect(data.contracts.length).toBeGreaterThan(0); // demo data, not empty
  });

  it("falls back on an HTTP error, not only on a network failure", async () => {
    // A 500 is the more common outage in practice, and `get` throws on !ok, so
    // it has to reach the same catch.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: false, status: 500 } as unknown as Response)),
    );

    const { live } = await fetchPriisDataWithFallback();

    expect(live).toBe(false);
  });

  it("never reports mock data as live", async () => {
    // The assertion that matters. If `live` were ever true on the fallback path,
    // an analyst would be reading demo records with no indication of it — and
    // nothing else in the return value would give it away.
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("down"))));

    const offline = await fetchPriisDataWithFallback();

    stubEndpoints({ "/contracts": [contract()] });
    const online = await fetchPriisDataWithFallback();

    expect(offline.live).toBe(false);
    expect(online.live).toBe(true);
    expect(offline.live).not.toBe(online.live);
  });

  it("does not throw when the backend is down", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("down"))));

    await expect(fetchPriisDataWithFallback()).resolves.toBeDefined();
  });
});

describe("fetchPriisData", () => {
  it("throws rather than returning a partial dataset when an endpoint fails", async () => {
    // Promise.all, so one bad endpoint fails the whole assembly. That is the
    // right call: a dataset missing only its contracts would render as an
    // investigation with no spending attached.
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        url.endsWith("/contracts")
          ? Promise.resolve({ ok: false, status: 503 } as unknown as Response)
          : Promise.resolve(okJson([])),
      ),
    );

    await expect(fetchPriisData()).rejects.toThrow(/503/);
  });

  it("names the failing path in the error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        url.endsWith("/anomalies")
          ? Promise.resolve({ ok: false, status: 404 } as unknown as Response)
          : Promise.resolve(okJson([])),
      ),
    );

    await expect(fetchPriisData()).rejects.toThrow(/\/anomalies/);
  });

  it("drops invalid rows without failing the whole request", async () => {
    stubEndpoints({ "/contracts": [contract({ id: "C-1" }), { id: "broken" }] });
    vi.spyOn(console, "warn").mockImplementation(() => undefined);

    const data = await fetchPriisData();

    expect(data.contracts.map((c) => c.id)).toEqual(["C-1"]);
  });
});

describe("deriveWatchlist (through fetchPriisData)", () => {
  // The backend has no watchlist endpoint, so it is computed here. Without it
  // the left-rail watchlist is empty in live mode while looking perfectly
  // healthy — an empty review queue reads as "nothing needs review".

  it("picks up high-band anomalies and flagged contracts", async () => {
    stubEndpoints({
      "/anomalies": [anomaly({ id: "A-hi", band: "hi" }), anomaly({ id: "A-lo", band: "lo" })],
      "/contracts": [
        contract({ id: "C-flagged", status: "flagged" }),
        contract({ id: "C-ok", status: "executed" }),
      ],
    });

    const { watchlist } = await fetchPriisData();
    const ids = watchlist.map((w) => w.id);

    expect(ids).toContain("A-hi");
    expect(ids).toContain("C-flagged");
    expect(ids).not.toContain("A-lo");
    expect(ids).not.toContain("C-ok");
  });

  it("tags each entry with its kind, so the rail can route the click", async () => {
    stubEndpoints({
      "/anomalies": [anomaly({ id: "A-hi", band: "hi" })],
      "/contracts": [contract({ id: "C-flagged", status: "flagged" })],
    });

    const { watchlist } = await fetchPriisData();

    expect(watchlist.find((w) => w.id === "A-hi")?.kind).toBe("anomaly");
    expect(watchlist.find((w) => w.id === "C-flagged")?.kind).toBe("contract");
  });

  it("caps the list at eight entries", async () => {
    stubEndpoints({
      "/anomalies": Array.from({ length: 12 }, (_, i) =>
        anomaly({ id: `A-${i}`, band: "hi" }),
      ),
    });

    const { watchlist } = await fetchPriisData();

    expect(watchlist).toHaveLength(8);
  });

  it("is empty when nothing needs review, without throwing", async () => {
    stubEndpoints({ "/anomalies": [anomaly({ band: "lo" })], "/contracts": [contract()] });

    const { watchlist } = await fetchPriisData();

    expect(watchlist).toEqual([]);
  });

  it("only counts rows that survived validation", async () => {
    // A flagged contract that fails the schema is not on the watchlist either —
    // worth knowing, because it means schema drift can quietly empty the review
    // queue rather than just shortening a table.
    stubEndpoints({ "/contracts": [{ id: "C-broken", status: "flagged" }] });
    vi.spyOn(console, "warn").mockImplementation(() => undefined);

    const { watchlist } = await fetchPriisData();

    expect(watchlist).toEqual([]);
  });
});
