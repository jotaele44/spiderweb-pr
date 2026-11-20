import { afterEach, describe, expect, it, vi } from "vitest";
import {
  datasetCenter,
  datasetContains,
  eriBaseUrl,
  eriCatalogSchema,
  eriFootprintsUrl,
  eriTileUrlTemplate,
  fetchEriCatalog,
  formatAcquired,
  formatBytes,
  type EriDataset,
} from "./eriApi";

const dataset: EriDataset = {
  id: "pre_event_2022_cb2201a",
  label: "2022 Pre-Event — Puerto Rico & USVI",
  event: "2022_Pre_Event",
  flight: "CB2201a_OB_N_RGB",
  kind: "pre_event",
  acquired: "2022",
  bbox: [-67.3, 17.66, -64.55, 18.53],
  min_zoom: 14,
  max_zoom: 20,
  source_url: "https://noaa-eri-pds.s3.amazonaws.com/index.html#2022_Pre_Event/CB2201a_OB_N_RGB/",
};
const catalog = { attribution: "NOAA", tile_size: 256, datasets: [dataset] };

afterEach(() => vi.unstubAllGlobals());

describe("ERI URLs", () => {
  it("anchors a same-origin API base to the page origin", () => {
    expect(eriBaseUrl("", "https://app.example")).toBe("https://app.example");
    expect(eriBaseUrl("/api/", "https://app.example")).toBe("https://app.example/api");
  });

  it("keeps an absolute API base", () => {
    expect(eriBaseUrl("http://localhost:8000/", "https://app.example")).toBe("http://localhost:8000");
  });

  it("builds the tile template and the footprint URL", () => {
    expect(eriTileUrlTemplate(dataset.id, "http://localhost:8000")).toBe(
      "http://localhost:8000/imagery/eri/pre_event_2022_cb2201a/tiles/{z}/{x}/{y}.png",
    );
    expect(eriFootprintsUrl(dataset.id, "", "https://app.example")).toBe(
      "https://app.example/imagery/eri/pre_event_2022_cb2201a/footprints.geojson",
    );
  });
});

describe("ERI catalog", () => {
  it("parses a valid catalog and rejects a malformed one", () => {
    expect(eriCatalogSchema.parse(catalog).datasets[0].id).toBe(dataset.id);
    expect(() => eriCatalogSchema.parse({ ...catalog, datasets: [{ ...dataset, bbox: [1, 2, 3] }] })).toThrow();
    expect(() => eriCatalogSchema.parse({ ...catalog, datasets: [{ ...dataset, kind: "other" }] })).toThrow();
  });

  it("fetches and validates the catalog", async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve(new Response(JSON.stringify(catalog))));
    vi.stubGlobal("fetch", fetchMock);
    await expect(fetchEriCatalog()).resolves.toMatchObject({ attribution: "NOAA", tile_size: 256 });
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/imagery\/eri\/datasets$/);
  });

  it("reports an HTTP failure", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("", { status: 503 }))));
    await expect(fetchEriCatalog()).rejects.toThrow("503");
  });
});

describe("ERI formatting and extent helpers", () => {
  it("formats a full date and leaves a bare year alone", () => {
    expect(formatAcquired("2017-09-24")).toBe("24 Sep 2017");
    expect(formatAcquired("2022")).toBe("2022");
  });

  it("formats sizes", () => {
    expect(formatBytes(65_703_333)).toBe("62.7 MB");
    expect(formatBytes(180_000)).toBe("176 KB");
    expect(formatBytes(0)).toBe("—");
  });

  it("tests containment and centre against the bbox", () => {
    expect(datasetContains(dataset, -66.1167, 18.4655)).toBe(true);
    expect(datasetContains(dataset, -70, 18.4655)).toBe(false);
    expect(datasetCenter(dataset)).toEqual([(-67.3 + -64.55) / 2, (17.66 + 18.53) / 2]);
  });
});
