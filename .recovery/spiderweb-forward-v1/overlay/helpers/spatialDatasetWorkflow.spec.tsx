import { assignDatasetRoles, buildCanonicalAnalysisReceipt, buildSpatialDatasets, buildUploadManifest, classifySpatialSource, evaluatePresetEligibility } from "./spatialDatasetWorkflow";

describe("Spiderweb manifest/preset/preflight workflow", () => {
  it("classifies supported source families without pretending unsupported containers are parsed", () => {
    expect(classifySpatialSource("a.geojson").format).toBe("geojson");
    expect(classifySpatialSource("a.kml").format).toBe("kml");
    expect(classifySpatialSource("a.tif").format).toBe("geotiff");
    expect(classifySpatialSource("a.gpkg").format).toBe("gpkg");
    expect(classifySpatialSource("a.zip").format).toBe("zip");
  });

  it("groups only authoritative Shapefile sidecars and blocks partial bundles", () => {
    const complete = buildUploadManifest([
      { path: "roads.shp", size: 1, sha256: "a".repeat(64) },
      { path: "roads.dbf", size: 2, sha256: "b".repeat(64) },
      { path: "roads.shx", size: 3, sha256: "c".repeat(64) },
      { path: "roads.prj", size: 4, sha256: "d".repeat(64) },
    ]);
    expect(complete.groups.length).toBe(1);
    expect(complete.groups[0].state).toBe("READY");
    const partial = buildUploadManifest([{ path: "roads.shp", size: 1 }, { path: "roads.dbf", size: 2 }]);
    expect(partial.groups[0].state).toBe("BLOCKED_PARTIAL");
    expect(partial.groups[0].reason).toContain("shx");
  });

  it("preserves archive containers independently instead of guessing their members", () => {
    const manifest = buildUploadManifest([{ path: "batch.zip", size: 99, sha256: "e".repeat(64) }]);
    expect(manifest.groups[0].state).toBe("PRESERVED_CONTAINER");
    const datasets = buildSpatialDatasets(manifest);
    expect(datasets[0].parserState).toBe("BLOCKED");
    expect(datasets[0].warnings.join(" ")).toContain("member classification");
  });

  it("keeps source manifestation IDs separate from runtime dataset IDs", () => {
    const manifest = buildUploadManifest([{ path: "a.geojson", size: 10, sha256: "1".repeat(64) }]);
    const sourceId = manifest.manifestations[0].sourceManifestationId;
    const datasets = buildSpatialDatasets(manifest, [{ sourceManifestationId: sourceId, parser: "geojson-v1", state: "PASS", declaredCrs: "EPSG:4326", featureCount: 2, exactFeatureIds: ["A", "B"], geometryTypes: ["Point"], capabilities: ["vector", "provenance"] }]);
    expect(datasets[0].sourceIdsAreRuntimeIds).toBeFalse();
    expect(datasets[0].runtimeDatasetId).not.toBe(sourceId);
    expect(datasets[0].sourceManifestationIds).toEqual([sourceId]);
  });

  it("fails closed on duplicate paths and conserves manifest arithmetic", () => {
    const manifest = buildUploadManifest([{ path: "a.geojson", size: 1 }, { path: "a.geojson", size: 1 }]);
    expect(manifest.duplicatePaths).toEqual(["a.geojson"]);
    expect(manifest.arithmetic.uploaded).toBe(2);
    expect(manifest.arithmetic.grouped).toBe(2);
    expect(manifest.arithmetic.ungrouped).toBe(0);
  });

  it("keeps GeoPackage blocked until a real adapter contract passes", () => {
    const manifest = buildUploadManifest([{ path: "authority.gpkg", size: 50, sha256: "2".repeat(64) }]);
    const sourceId = manifest.manifestations[0].sourceManifestationId;
    let datasets = buildSpatialDatasets(manifest, [{ sourceManifestationId: sourceId, parser: "gpkg-placeholder", state: "PASS", declaredCrs: "EPSG:4326", capabilities: ["vector"], exactFeatureIds: ["A"] }]);
    datasets = assignDatasetRoles(datasets, { [datasets[0].runtimeDatasetId]: "PRIMARY" });
    const preflight = evaluatePresetEligibility("topology_review", datasets);
    expect(preflight.state).toBe("BLOCKED");
    expect(preflight.issues.some((row) => row.code === "GEOPACKAGE_BLOCKED")).toBeTrue();
  });

  it("fails closed on mixed CRS and duplicate exact feature IDs", () => {
    const manifest = buildUploadManifest([{ path: "a.geojson", size: 1, sha256: "3".repeat(64) }, { path: "b.geojson", size: 1, sha256: "4".repeat(64) }]);
    const [a,b] = manifest.manifestations;
    let datasets = buildSpatialDatasets(manifest, [
      { sourceManifestationId: a.sourceManifestationId, parser: "geojson-v1", state: "PASS", declaredCrs: "EPSG:4326", exactFeatureIds: ["A"], duplicateFeatureIds: ["A"], geometryTypes: ["Point"], capabilities: ["vector", "provenance"] },
      { sourceManifestationId: b.sourceManifestationId, parser: "geojson-v1", state: "PASS", declaredCrs: "EPSG:3857", exactFeatureIds: ["B"], geometryTypes: ["Point"], capabilities: ["vector", "provenance"] },
    ]);
    datasets = assignDatasetRoles(datasets, { [datasets[0].runtimeDatasetId]: "PRIMARY", [datasets[1].runtimeDatasetId]: "COMPARISON" });
    const preflight = evaluatePresetEligibility("source_equivalence", datasets);
    expect(preflight.state).toBe("BLOCKED");
    expect(preflight.issues.some((row) => row.code === "DUPLICATE_FEATURE_IDS")).toBeTrue();
  });

  it("rejects unsupported geometries explicitly", () => {
    const manifest = buildUploadManifest([{ path: "a.geojson", size: 1, sha256: "5".repeat(64) }]);
    const sourceId = manifest.manifestations[0].sourceManifestationId;
    let datasets = buildSpatialDatasets(manifest, [{ sourceManifestationId: sourceId, parser: "geojson-v1", state: "PASS", declaredCrs: "EPSG:4326", exactFeatureIds: ["A"], geometryTypes: ["GeometryCollection"], capabilities: ["vector"] }]);
    datasets = assignDatasetRoles(datasets, { [datasets[0].runtimeDatasetId]: "PRIMARY" });
    const preflight = evaluatePresetEligibility("topology_review", datasets);
    expect(preflight.state).toBe("BLOCKED");
    expect(preflight.issues.some((row) => row.code === "UNSUPPORTED_GEOMETRY")).toBeTrue();
  });

  it("fails closed on role ties instead of silently choosing a dataset", () => {
    const manifest = buildUploadManifest([{ path: "a.geojson", size: 1 }, { path: "b.geojson", size: 1 }]);
    const evidence = manifest.manifestations.map((row, index) => ({ sourceManifestationId: row.sourceManifestationId, parser: "geojson-v1", state: "PASS" as const, declaredCrs: "EPSG:4326", exactFeatureIds: [String(index)], geometryTypes: ["Point"], capabilities: ["vector"] }));
    let datasets = buildSpatialDatasets(manifest, evidence);
    datasets = assignDatasetRoles(datasets, Object.fromEntries(datasets.map((row) => [row.runtimeDatasetId, "PRIMARY"])) as Record<string, "PRIMARY">);
    const preflight = evaluatePresetEligibility("topology_review", datasets);
    expect(preflight.state).toBe("BLOCKED");
    expect(preflight.issues.some((row) => row.code === "AMBIGUOUS_ROLE_ASSIGNMENT")).toBeTrue();
  });

  it("allows heterogeneous formats only when capabilities and identity gates close", () => {
    const manifest = buildUploadManifest([{ path: "a.geojson", size: 1, sha256: "6".repeat(64) }, { path: "b.kml", size: 1, sha256: "7".repeat(64) }]);
    const [a,b] = manifest.manifestations;
    let datasets = buildSpatialDatasets(manifest, [
      { sourceManifestationId: a.sourceManifestationId, parser: "geojson-v1", state: "PASS", declaredCrs: "EPSG:4326", exactFeatureIds: ["A"], geometryTypes: ["Point"], capabilities: ["vector", "provenance"] },
      { sourceManifestationId: b.sourceManifestationId, parser: "kml-v1", state: "PASS", declaredCrs: "EPSG:4326", exactFeatureIds: ["A"], geometryTypes: ["Point"], capabilities: ["vector", "provenance"] },
    ]);
    datasets = assignDatasetRoles(datasets, { [datasets[0].runtimeDatasetId]: "PRIMARY", [datasets[1].runtimeDatasetId]: "COMPARISON" });
    expect(evaluatePresetEligibility("source_equivalence", datasets).state).toBe("PASS");
  });

  it("keeps RAW NORMALIZED CANONICAL provenance separate and emits deterministic receipts", () => {
    const manifest = buildUploadManifest([{ path: "a.geojson", size: 1, sha256: "8".repeat(64) }]);
    const sourceId = manifest.manifestations[0].sourceManifestationId;
    let datasets = buildSpatialDatasets(manifest, [{ sourceManifestationId: sourceId, parser: "geojson-v1", state: "PASS", declaredCrs: "EPSG:4326", featureCount: 1, exactFeatureIds: ["A"], geometryTypes: ["Point"], capabilities: ["vector"] }]);
    datasets = assignDatasetRoles(datasets, { [datasets[0].runtimeDatasetId]: "PRIMARY" });
    expect(datasets[0].provenance.raw.manifestationIds).toEqual([sourceId]);
    expect(datasets[0].provenance.normalized.state).toBe("AVAILABLE");
    expect(datasets[0].provenance.canonical.state).toBe("ELIGIBLE");
    const one = buildCanonicalAnalysisReceipt(manifest, "topology_review", datasets);
    const two = buildCanonicalAnalysisReceipt(manifest, "topology_review", datasets);
    expect(one.state).toBe("PASS");
    expect(one.receiptKey).toBe(two.receiptKey);
    expect(one.conservation.unexplainedResidue).toBe(0);
    expect(one.graph.map((row) => row.stage)).toEqual(["INGEST_MANIFEST", "CLASSIFY_SOURCES", "PARSE_WITH_CONTRACTS", "NORMALIZE_WITHOUT_OVERWRITING_RAW", "PREFLIGHT", "ANALYZE", "RECEIPT"]);
  });
});