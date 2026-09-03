import type * as maplibregl from "maplibre-gl";
import type { SpatialSceneConfig } from "../runtime/SpatialRuntime";

const rasterStyle: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

// This center/zoom is independent of the gebco/terrain.py PR_LON_MIN/PR_LAT_MIN
// bounding envelope — the two currently have no shared source of truth for
// "where is Puerto Rico." Worth reconciling once a real analytical-domain
// registry exists; out of scope for this config move.
export const DEFAULT_REGIONAL_SCENE_CONFIG: SpatialSceneConfig = {
  basemapStyle: rasterStyle,
  basemapSourceId: "osm",
  initialView: {
    center: [-66.35, 18.22],
    zoom: 8.4,
  },
};
