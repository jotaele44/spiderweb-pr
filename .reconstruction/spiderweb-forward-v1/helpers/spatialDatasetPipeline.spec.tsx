import {
  applyDatasetObservations,
  buildAnalysisReceipt,
  buildSpatialDatasets,
  buildUploadManifest,
  classifyUploadKind,
  closeDatasetArithmetic,
  preflightAnalysis,
  presetEligibility,
} from "./spatialDatasetPipeline";

describe("Spiderweb upload manifest and dataset pipeline", () => {
  it("classifies supported files and preserves independent manifestations", () => {
    const manifest = buildUploadManifest([
      { name: "a.geojson", size: 10, sha256: "AA" },
      { name: "b.csv", size: 20, sha256: "BB" },
      { name: "c.gpkg", size: 30, sha256: "CC" },
    ]);
    expect(manifest.map(row => row.kind)).toEqual(["geojson", "csv", "gpkg"]);
    expect(new Set(manifest.map(row => row.sourceId)).size).toBe(3);
    expect(new Set(manifest.map(row => row.runtimeId)).size).toBe(3);
    expect(manifest[0].sourceId).not.toBe(manifest[0].runtimeId);
  });

  it("groups only exact-stem Shapefile sidecars", () => {
    const manifest = buildUploadManifest([
      { name: "roads.shp", size: 1 }, { name: "roads.shx", size: 1 }, { name: "roads.dbf", size: 1 },
      { name: "other.prj", size: 1 },
    ]);
    const datasets = buildSpatialDatasets(manifest);
    expect(datasets[0].format).toBe("SHAPEFILE");
    expect(datasets[0].sourceIds.length).toBe(3);
    expect(datasets.some(row => row.sourceIds.length === 1 && row.state === "BLOCKED")).toBeTrue();
  });

  it("fails closed on partial Shapefiles", () => {
    const datasets = buildSpatialDatasets(buildUploadManifest([{ name: "roads.shp", size: 1 }, { name: "roads.dbf", size: 1 }]));
    expect(datasets[0].state).toBe("BLOCKED");
    expect(datasets[0].issues.some(row => row.code === "PARTIAL_SHAPEFILE")).toBeTrue();
  });

  it("fails closed on sidecar ties instead of picking a candidate", () => {
    const datasets = buildSpatialDatasets(buildUploadManifest([
      { name: "roads.shp", size: 1 }, { name: "roads.shx", size: 1 }, { name: "roads.dbf", size: 1 }, { name: "roads.DBF", size: 2 },
    ]));
    expect(datasets[0].state).toBe("BLOCKED");
    expect(datasets[0].issues.some(row => row.code === "SIDECAR_TIE")).toBeTrue();
  });

  it("does not auto-group archive containers with neighboring files", () => {
    const datasets = buildSpatialDatasets(buildUploadManifest([{ name: "bundle.zip", size: 1 }, { name: "bundle.geojson", size: 2 }]));
    expect(datasets.length).toBe(2);
    expect(datasets.find(row => row.format === "ZIP")?.issues[0].code).toBe("ARCHIVE_RELATION_UNPROVEN");
  });

  it("keeps GeoPackage blocked until a genuine adapter exists", () => {
    const datasets = buildSpatialDatasets(buildUploadManifest([{ name: "parcel.gpkg", size: 1 }]));
    expect(datasets[0].state).toBe("BLOCKED");
    expect(datasets[0].issues[0].code).toBe("GEOPACKAGE_BLOCKED");
  });

  it("keeps raster uploads blocked behind specialized adapter contracts", () => {
    const datasets = buildSpatialDatasets(buildUploadManifest([{ name: "dem.tif", size: 1 }]));
    expect(datasets[0].capabilities).toContain("RASTER");
    expect(datasets[0].issues[0].code).toBe("RASTER_ADAPTER_UNVERIFIED");
  });

  it("derives preset eligibility from actual dataset capabilities", () => {
    const datasets = buildSpatialDatasets(buildUploadManifest([{ name: "left.geojson", size: 1 }, { name: "right.geojson", size: 1 }]));
    expect(presetEligibility("EXACT_ID_DIFF", datasets).eligible).toBeTrue();
    expect(presetEligibility("TERRAIN_CANDIDATES", datasets).eligible).toBeFalse();
  });

  it("enables terrain preset only after observed terrain attributes exist", () => {
    let datasets = buildSpatialDatasets(buildUploadManifest([{ name: "terrain.geojson", size: 1 }]));
    datasets = applyDatasetObservations(datasets, [{ datasetId: datasets[0].datasetId, hasTerrainAttributes: true }]);
    expect(presetEligibility("TERRAIN_CANDIDATES", datasets).eligible).toBeTrue();
  });

  it("blocks mixed CRS until a verified transform resolves the difference", () => {
    let datasets = buildSpatialDatasets(buildUploadManifest([{ name: "a.geojson", size: 1 }, { name: "b.geojson", size: 1 }]));
    datasets = applyDatasetObservations(datasets, [
      { datasetId: datasets[0].datasetId, declaredCrs: "EPSG:4326" },
      { datasetId: datasets[1].datasetId, declaredCrs: "EPSG:32161" },
    ]);
    const result = preflightAnalysis("EXACT_ID_DIFF", datasets);
    expect(result.state).toBe("BLOCK");
    expect(result.issues.some(row => row.code === "MIXED_CRS_UNRESOLVED")).toBeTrue();
  });

  it("blocks duplicate feature IDs and unsupported geometry residue", () => {
    let datasets = buildSpatialDatasets(buildUploadManifest([{ name: "a.geojson", size: 1 }]));
    datasets = applyDatasetObservations(datasets, [{
      datasetId: datasets[0].datasetId,
      duplicateIds: ["x", "x"],
      unsupportedGeometryCount: 1,
    }]);
    expect(datasets[0].state).toBe("BLOCKED");
    expect(datasets[0].issues.some(row => row.code === "DUPLICATE_FEATURE_IDS")).toBeTrue();
    expect(datasets[0].issues.some(row => row.code === "UNSUPPORTED_GEOMETRY")).toBeTrue();
  });

  it("keeps unidentified and null geometry residue visible as review", () => {
    let datasets = buildSpatialDatasets(buildUploadManifest([{ name: "a.geojson", size: 1 }]));
    datasets = applyDatasetObservations(datasets, [{ datasetId: datasets[0].datasetId, unidentifiedCount: 2, nullGeometryCount: 1 }]);
    expect(datasets[0].state).toBe("REVIEW");
    expect(preflightAnalysis("TOPOLOGY_REVIEW", datasets).state).toBe("REVIEW");
  });

  it("closes manifestation arithmetic without dropping heterogeneous uploads", () => {
    const manifest = buildUploadManifest([
      { name: "a.geojson", size: 1 }, { name: "b.csv", size: 1 },
      { name: "roads.shp", size: 1 }, { name: "roads.shx", size: 1 }, { name: "roads.dbf", size: 1 },
      { name: "archive.zip", size: 1 }, { name: "surface.tif", size: 1 },
    ]);
    const closure = closeDatasetArithmetic(manifest, buildSpatialDatasets(manifest));
    expect(closure.inputManifestations).toBe(7);
    expect(closure.boundManifestations).toBe(7);
    expect(closure.unboundManifestations).toEqual([]);
    expect(closure.duplicateBindings).toEqual([]);
    expect(closure.closed).toBeTrue();
  });

  it("produces deterministic receipts and one canonical analysis graph", () => {
    const datasets = buildSpatialDatasets(buildUploadManifest([
      { name: "a.geojson", size: 1, sha256: "aa" },
      { name: "b.geojson", size: 1, sha256: "bb" },
    ]));
    const first = buildAnalysisReceipt("EXACT_ID_DIFF", datasets);
    const second = buildAnalysisReceipt("EXACT_ID_DIFF", datasets);
    expect(first.fingerprint).toBe(second.fingerprint);
    expect(first.graph.map(row => row.kind)).toEqual(["MANIFEST", "DATASET", "DATASET", "PREFLIGHT", "ANALYSIS", "RECEIPT"]);
    expect(first.planes).toEqual(["RAW", "NORMALIZED", "CANONICAL"]);
    expect(first.authority).toBe("ANALYSIS_ONLY");
  });

  it("classifies extension aliases deterministically", () => {
    expect(classifyUploadKind("A.GEOJSON")).toBe("geojson");
    expect(classifyUploadKind("A.TIFF")).toBe("tiff");
    expect(classifyUploadKind("README")).toBe("unknown");
  });
});