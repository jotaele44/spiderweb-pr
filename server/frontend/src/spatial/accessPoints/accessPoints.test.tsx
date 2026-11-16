import { act, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type * as maplibregl from "maplibre-gl";
import { EDGE_STYLE, RelationshipGraph, RENDER_CLASS_ORDER } from "../../components/RelationshipGraph";
import { coveredRuns, SYNTHETIC_BANNER, TransectProfile } from "../transect/TransectProfile";
import { crossSectionSchema } from "../transect/transectApi";
import { AccessPointDetail, PROVISIONAL_SENTENCE } from "./AccessPointDetail";
import { toGraph } from "./AccessPointRelationships";
import * as api from "./accessPointsApi";
import {
  ACCESS_POINT_SOURCE_IDS,
  accessPointLayerIds,
  applyAccessPointLayers,
  partitionFeatures,
  pointPaint,
  removeAccessPointLayers,
  statusesForGroups,
} from "./accessPointLayers";
import { AccessPointsPanel, registryStatusText } from "./AccessPointsPanel";
import * as fx from "./fixtures";
import { SourceCoveragePanel } from "./SourceCoveragePanel";
import { useAccessPointsController, type AccessPointsControllerState, type RegistryView } from "./useAccessPointsController";

const collection = (features: api.AccessPointFeature[]) => ({
  type: "FeatureCollection",
  features,
  number_matched: features.length,
  number_returned: features.length,
  unlocated_count: features.filter((f) => f.geometry === null).length,
  next_cursor: null,
  crs: "OGC:CRS84",
  provenance: fx.provenance,
  scope: fx.scope,
});

interface FakeLayer { id: string; source: string; filter?: unknown; paint?: Record<string, unknown> }

function fakeMap() {
  const sources = new Map<string, { data: unknown }>();
  const layers: FakeLayer[] = [];
  const once: Record<string, (() => void)[]> = {};
  const handlers: { event: string; layer: string }[] = [];
  const map = {
    getStyle: () => ({ layers: [{ id: "labels", type: "symbol" }] }),
    isStyleLoaded: () => true,
    getSource: (id: string) => {
      const source = sources.get(id);
      return source ? { setData: (data: unknown) => { source.data = data; } } : undefined;
    },
    addSource: (id: string, spec: { data: unknown }) => { sources.set(id, { data: spec.data }); },
    removeSource: (id: string) => { sources.delete(id); },
    getLayer: (id: string) => layers.find((layer) => layer.id === id),
    addLayer: (layer: FakeLayer) => { layers.push(layer); },
    removeLayer: (id: string) => { layers.splice(layers.findIndex((layer) => layer.id === id), 1); },
    setFilter: (id: string, filter: unknown) => { const layer = layers.find((l) => l.id === id); if (layer) layer.filter = filter; },
    setPaintProperty: () => undefined,
    once: (event: string, callback: () => void) => { (once[event] ??= []).push(callback); },
    on: (event: string, layer: string) => { handlers.push({ event, layer }); },
    off: () => undefined,
  };
  const fire = (event: string) => { (once[event] ?? []).splice(0).forEach((callback) => callback()); };
  return { map: map as unknown as maplibregl.Map, sources, layers, handlers, fire };
}

describe("API contract", () => {
  it("accepts a well-formed registry page", () => {
    const parsed = api.featureCollectionSchema.parse(collection([fx.seed, fx.candidate, fx.verified]));
    expect(parsed.features).toHaveLength(3);
    expect(parsed.features[0].geometry).toBeNull();
  });

  it.each([
    ["verification its status does not carry", { ...fx.candidate, properties: { ...fx.candidate.properties, is_verified: true } }],
    ["geometry it does not have", { ...fx.seed, properties: { ...fx.seed.properties, has_geometry: true } }],
    ["an unknown status", { ...fx.candidate, properties: { ...fx.candidate.properties, status: "CONFIRMED" } }],
    ["an out-of-range coordinate", { ...fx.candidate, geometry: { type: "Point", coordinates: [-266.1, 17.9] } }],
  ])("rejects a record claiming %s", (_name, bad) => {
    expect(api.featureCollectionSchema.safeParse(collection([bad as api.AccessPointFeature])).success).toBe(false);
  });

  it("rejects a page in another coordinate system and a link drawn as verified without being verified", () => {
    expect(api.featureCollectionSchema.safeParse({ ...collection([fx.candidate]), crs: "EPSG:32620" }).success).toBe(false);
    const document = fx.relationships(["hypothesized"]);
    document.relationships[0].render_class = "verified";
    expect(api.relationshipsSchema.safeParse(document).success).toBe(false);
    expect(api.relationshipsSchema.safeParse(fx.relationships(["verified", "hypothesized"])).success).toBe(true);
  });

  it("builds one endpoint per registry and never a merged one", () => {
    expect(api.featuresUrl("inland", { limit: 5 }, "")).toBe("/v1/access-points/inland/features?limit=5");
    expect(api.featuresUrl("offshore", {}, "")).toBe("/v1/access-points/offshore/features");
    expect(api.evidenceUrl("offshore", "OFAP-PR-000006", "")).toBe("/v1/access-points/offshore/features/OFAP-PR-000006/evidence");
    expect(api.shortHash("ab".repeat(32))).toHaveLength(12);
    expect(api.statusGroup("UNDER_REVIEW")).toBe("candidate");
    expect(api.statusGroup("SUPERSEDED")).toBe("retired");
  });

  it("treats a malformed response as an error, not as an empty registry", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({ type: "FeatureCollection", features: [] }), { status: 200 }))));
    await expect(api.fetchOffshoreFeatures()).rejects.toBeInstanceOf(api.AccessPointsContractError);
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: "registry document has not been built" }), { status: 503 }))));
    await expect(api.fetchInlandFeatures()).rejects.toBeInstanceOf(api.AccessPointsRequestError);
    vi.unstubAllGlobals();
  });
});

describe("map layers", () => {
  it("draws only records with registered point coordinates", () => {
    const { mapData, notDrawn } = partitionFeatures([fx.seed, fx.candidate, fx.verified, fx.rejected]);
    expect(mapData.features.map((f) => f.id)).toEqual(["OFAP-PR-000006", "OFAP-PR-000007"]);
    expect(notDrawn.map((r) => [r.feature.id, r.reason])).toEqual([
      ["OFAP-PR-000001", "no-coordinates"],
      ["OFAP-PR-000008", "retired"],
    ]);
  });

  it("tells status apart by shape, not only by colour", () => {
    const paint = pointPaint("offshore");
    expect(paint["circle-opacity"]).toEqual(["match", ["get", "status"], "VERIFIED", 1, "PROVISIONAL_DISCOVERY", 0, 0]);
    expect(paint["circle-radius"]).toEqual(["match", ["get", "status"], "VERIFIED", 6.5, "PROVISIONAL_DISCOVERY", 3.5, 6]);
    expect(statusesForGroups({ verified: true, candidate: false, provisional: false })).toEqual(["VERIFIED"]);
  });

  it("keeps the two registries in separate sources and layers", () => {
    const { map, sources, layers } = fakeMap();
    const data = partitionFeatures([fx.candidate]).mapData;
    applyAccessPointLayers(map, "inland", data, ["CANDIDATE"]);
    applyAccessPointLayers(map, "offshore", data, ["CANDIDATE"]);
    applyAccessPointLayers(map, "offshore", data, ["CANDIDATE"]); // idempotent
    expect([...sources.keys()].sort()).toEqual([ACCESS_POINT_SOURCE_IDS.inland, ACCESS_POINT_SOURCE_IDS.offshore].sort());
    expect(layers).toHaveLength(6);
    expect(layers.every((layer) => layer.id.startsWith(layer.source))).toBe(true);
    removeAccessPointLayers(map, "inland");
    expect([...sources.keys()]).toEqual([ACCESS_POINT_SOURCE_IDS.offshore]);
    expect(layers.map((layer) => layer.id).sort()).toEqual(Object.values(accessPointLayerIds("offshore")).sort());
  });
});

function view(overrides: Partial<RegistryView> & { registry: RegistryView["registry"] }): RegistryView {
  return { enabled: false, state: "off", error: null, snapshot: null, drawnCount: 0, notDrawn: [], ...overrides };
}

function controller(overrides: Partial<AccessPointsControllerState> = {}): AccessPointsControllerState {
  return {
    registries: [view({ registry: "inland" }), view({ registry: "offshore" })],
    groups: { verified: true, candidate: true, provisional: true },
    statusGroups: api.DRAWN_STATUS_GROUPS,
    toggleRegistry: vi.fn(),
    toggleGroup: vi.fn(),
    selection: null,
    selectedFeature: null,
    select: vi.fn(),
    evidence: { status: "idle" },
    coverageRegistry: null,
    setCoverageRegistry: vi.fn(),
    coverage: { status: "idle" },
    ...overrides,
  };
}

const snapshot = (features: api.AccessPointFeature[]) => ({
  features,
  numberMatched: features.length,
  truncated: false,
  provenance: fx.provenance,
  scope: fx.scope,
});

describe("AccessPointsPanel", () => {
  it("never says a registry is drawn before the map has drawn it", () => {
    expect(registryStatusText(view({ registry: "inland", enabled: true, state: "source-ready", drawnCount: 4 }))).not.toMatch(/drawn on the map/);
    expect(registryStatusText(view({ registry: "inland", enabled: true, state: "loaded", drawnCount: 4 }))).toBe("4 drawn on the map");
  });

  it("lists records without coordinates instead of placing them", () => {
    const offshore = view({
      registry: "offshore",
      enabled: true,
      state: "loaded",
      snapshot: snapshot([fx.seed, fx.candidate]),
      drawnCount: 1,
      notDrawn: partitionFeatures([fx.seed, fx.candidate]).notDrawn,
    });
    const state = controller({ registries: [view({ registry: "inland" }), offshore] });
    render(<AccessPointsPanel controller={state} />);
    expect(screen.getByText(/1 record has no registered coordinates and is not drawn/)).toBeTruthy();
    const list = screen.getByRole("list", { name: /Off-Shore Access Points records not drawn/ });
    fireEvent.click(within(list).getByRole("button", { name: "OFAP-PR-000001" }));
    expect(state.select).toHaveBeenCalledWith({ registry: "offshore", featureId: "OFAP-PR-000001" });
    expect(within(list).getByText(/OSAP-SEED-001/)).toBeTruthy();
    expect(screen.getByText(/No halo means the uncertainty is unknown, not zero/)).toBeTruthy();
    expect(screen.getByText(/sha256 abababababab/)).toBeTruthy();
  });

  it("reports one registry's failure without hiding the other", () => {
    const state = controller({
      registries: [
        view({ registry: "inland", enabled: true, state: "error", error: "registry document failed verification" }),
        view({ registry: "offshore", enabled: true, state: "loaded", snapshot: snapshot([fx.candidate]), drawnCount: 1 }),
      ],
    });
    render(<AccessPointsPanel controller={state} />);
    expect(screen.getByRole("alert").textContent).toMatch(/Inland Access Points could not be loaded: registry document failed verification/);
    expect(screen.getByText("1 drawn on the map")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Inland Access Points" }));
    expect(state.toggleRegistry).toHaveBeenCalledWith("inland");
    fireEvent.click(screen.getByRole("button", { name: "Provisional" }));
    expect(state.toggleGroup).toHaveBeenCalledWith("provisional");
  });
});

describe("AccessPointDetail", () => {
  it("states plainly what a provisional record does not contain", () => {
    render(<AccessPointDetail feature={fx.seed} evidence={{ status: "idle" }} />);
    expect(screen.getByText(PROVISIONAL_SENTENCE)).toBeTruthy();
    expect(screen.getByText("no registered coordinates")).toBeTruthy();
    expect(screen.getByText(/OSAP-SEED-001/)).toBeTruthy();
    const current = screen.getByRole("list", { name: "What the evidence establishes" }).querySelector('[aria-current="step"]');
    expect(current?.textContent).toMatch(/^anomaly/);
  });

  it("shows when the evidence rules lowered an asserted tier, and why the record is not verified", () => {
    render(<AccessPointDetail feature={fx.candidate} evidence={{ status: "ready", evidence: fx.evidence }} />);
    expect(screen.getByText(/Asserted as direct; the evidence rules lowered it to candidate\./)).toBeTruthy();
    expect(screen.getAllByText(/the evidence rules lowered it/)).toHaveLength(1);
    expect(screen.getByText(/needs a directly observed physical opening/)).toBeTruthy();
    expect(screen.getByText("±25 m")).toBeTruthy();
  });

  it("keeps surveyed, published and retrieved dates apart and never blank", () => {
    render(<AccessPointDetail feature={fx.candidate} evidence={{ status: "ready", evidence: fx.evidence }} />);
    const dates = document.querySelectorAll(".ap-date");
    expect([...dates].map((node) => node.textContent)).toEqual([
      "Surveyed not recorded",
      "Published 2025-06-01",
      "Retrieved 2026-11-15T00:00:00Z",
    ]);
  });

  it("says the uncertainty is unknown rather than zero, and reports a failed evidence load", () => {
    const unknown = fx.feature({ id: "OFAP-PR-000009" });
    render(<AccessPointDetail feature={unknown} evidence={{ status: "error", message: "503" }} />);
    expect(screen.getByText("unknown")).toBeTruthy();
    expect(screen.queryByText(/±0/)).toBeNull();
    expect(screen.getByRole("alert").textContent).toMatch(/Evidence could not be loaded: 503/);
  });
});

describe("SourceCoveragePanel", () => {
  it("says that a listed source is not a measurement", () => {
    render(<SourceCoveragePanel registry="offshore" state={{ status: "ready", coverage: fx.coverage }} />);
    expect(screen.getByText(/0 of 1 sources are held, hashed direct measurements/)).toBeTruthy();
    expect(screen.getByText(/inventory coverage is not a measurement/)).toBeTruthy();
  });
});

describe("RelationshipGraph", () => {
  it("gives every class its own line pattern and its own text label", () => {
    const patterns = RENDER_CLASS_ORDER.map((renderClass) => EDGE_STYLE[renderClass].dash);
    expect(new Set(patterns).size).toBe(RENDER_CLASS_ORDER.length);
    expect(EDGE_STYLE.verified.dash).toBe("none");
    const graph = toGraph(fx.relationships([...RENDER_CLASS_ORDER]));
    const { container } = render(<RelationshipGraph {...graph} />);
    for (const renderClass of RENDER_CLASS_ORDER) {
      const line = container.querySelector(`line[data-render-class="${renderClass}"]`);
      expect(line?.getAttribute("stroke-dasharray")).toBe(EDGE_STYLE[renderClass].dash);
      expect(container.querySelector(`g[data-render-class="${renderClass}"] .relationship-edge-label`)?.textContent).toBe(renderClass);
    }
  });

  it("never draws a hypothesised link the way a verified one is drawn", () => {
    const { container } = render(<RelationshipGraph {...toGraph(fx.relationships(["verified", "hypothesized"]))} />);
    const verified = container.querySelector('svg[role="img"] line[data-render-class="verified"]');
    const hypothesised = container.querySelector('svg[role="img"] line[data-render-class="hypothesized"]');
    expect(hypothesised?.getAttribute("stroke-dasharray")).not.toBe(verified?.getAttribute("stroke-dasharray"));
    expect(hypothesised?.getAttribute("stroke-dasharray")).not.toBe("none");
  });

  it("says so when no relationship is recorded", () => {
    render(<RelationshipGraph {...toGraph(fx.relationships([]))} />);
    expect(screen.getByRole("status").textContent).toBe("No relationships are recorded between these registries.");
  });
});

describe("TransectProfile", () => {
  it("accepts a well-formed section and rejects one whose flags disagree", () => {
    expect(crossSectionSchema.safeParse(fx.crossSection(false)).success).toBe(true);
    expect(crossSectionSchema.safeParse({ ...fx.crossSection(false), is_continuous: true }).success).toBe(false);
    expect(crossSectionSchema.safeParse({ ...fx.crossSection(true), common_datum: null }).success).toBe(false);
  });

  it("never bridges a stretch with no survey coverage", () => {
    const profile = { source_id: null, kind: "BATHYMETRY", datum: "MLLW", covered_fraction: 0.6, samples: [0, 10, 20, 30, 40].map((d, i) => ({ distance_m: d, xy: [d, 0] as [number, number], elevation_m: i === 2 ? null : -5, uncertainty_m: i === 2 ? null : 0.2, interpolated: null })) };
    expect(coveredRuns(profile).map((run) => run.map((point) => point.distance))).toEqual([[0, 10], [30, 40]]);
    const { container } = render(<TransectProfile section={fx.crossSection(false)} />);
    expect(container.querySelectorAll("[data-gap]").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/no survey coverage/).length).toBeGreaterThan(0);
    expect(screen.getByText(/nothing is interpolated across it/)).toBeTruthy();
  });

  it("draws separate panels when the datums cannot be joined, and one when they can", () => {
    const separate = render(<TransectProfile section={fx.crossSection(false)} />);
    expect(separate.container.querySelectorAll("figure.transect-plot")).toHaveLength(2);
    expect([...separate.container.querySelectorAll("figure.transect-plot")].map((f) => f.getAttribute("data-datum"))).toEqual(["PRVD02", "MLLW"]);
    expect(screen.getByText(/no difference between them is computed: no certified transform between MLLW and PRVD02/)).toBeTruthy();
    separate.unmount();
    const joined = render(<TransectProfile section={fx.crossSection(true)} />);
    expect(joined.container.querySelectorAll("figure.transect-plot")).toHaveLength(1);
    expect(joined.container.querySelectorAll("[data-uncertainty-band]").length).toBe(2);
  });

  it("labels synthetic control data wherever it is shown", () => {
    render(<TransectProfile section={fx.crossSection(false)} />);
    expect(screen.getByRole("alert").textContent).toBe(SYNTHETIC_BANNER);
  });
});

describe("useAccessPointsController", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("loads each registry on its own and reaches 'loaded' only when the map has drawn it", async () => {
    const { map, sources, fire } = fakeMap();
    vi.spyOn(api, "fetchRegistrySnapshot").mockImplementation((registry) =>
      registry === "inland" ? Promise.reject(new Error("registry document failed verification")) : Promise.resolve(snapshot([fx.seed, fx.candidate])),
    );
    const mapRef = { current: map };
    const { result } = renderHook(() => useAccessPointsController({ mapRef, ready: true }));
    expect(result.current.registries.map((r) => r.state)).toEqual(["off", "off"]);
    act(() => { result.current.toggleRegistry("inland"); result.current.toggleRegistry("offshore"); });
    expect(result.current.registries.map((r) => r.state)).toEqual(["loading", "loading"]);
    await waitFor(() => expect(result.current.registries[1].state).toBe("source-ready"));
    expect(result.current.registries[0].state).toBe("error");
    expect(result.current.registries[0].error).toMatch(/failed verification/);
    expect(result.current.registries[1].drawnCount).toBe(1);
    expect(result.current.registries[1].notDrawn.map((r) => r.feature.id)).toEqual(["OFAP-PR-000001"]);
    expect([...sources.keys()]).toEqual([ACCESS_POINT_SOURCE_IDS.offshore]);
    act(() => fire("idle"));
    expect(result.current.registries[1].state).toBe("loaded");
    act(() => result.current.toggleRegistry("offshore"));
    expect(result.current.registries[1].state).toBe("off");
    expect(sources.size).toBe(0);
  });

  it("tolerates a missing map (3D mode) and loads evidence for a selection", async () => {
    vi.spyOn(api, "fetchRegistrySnapshot").mockResolvedValue(snapshot([fx.candidate]));
    vi.spyOn(api, "fetchAccessPointEvidence").mockResolvedValue(fx.evidence);
    const mapRef = { current: null };
    const { result } = renderHook(() => useAccessPointsController({ mapRef, ready: false }));
    act(() => result.current.toggleRegistry("offshore"));
    await waitFor(() => expect(result.current.registries[1].state).toBe("source-ready"));
    act(() => result.current.select({ registry: "offshore", featureId: "OFAP-PR-000006" }));
    expect(result.current.evidence.status).toBe("loading");
    await waitFor(() => expect(result.current.evidence.status).toBe("ready"));
    expect(result.current.selectedFeature?.id).toBe("OFAP-PR-000006");
    act(() => result.current.select(null));
    expect(result.current.evidence.status).toBe("idle");
  });
});
