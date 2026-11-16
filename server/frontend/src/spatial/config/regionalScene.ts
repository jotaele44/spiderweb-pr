import type * as maplibregl from "maplibre-gl";
import type { SpatialSceneConfig } from "../runtime/SpatialRuntime";
import { TILE_ATTRIBUTION, TILE_URL } from "../../config";

/** Source id and layer id of the base map within the regional style. */
export const BASEMAP_ID = "osm";

// The id stays "osm" for the default tiles and for a `VITE_TILE_URL` override
// alike: it names the base-map slot (error scoping, visibility toggle), not
// the provider.
const rasterStyle: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    [BASEMAP_ID]: {
      type: "raster",
      tiles: [TILE_URL],
      tileSize: 256,
      attribution: TILE_ATTRIBUTION,
    },
  },
  layers: [{ id: BASEMAP_ID, type: "raster", source: BASEMAP_ID }],
};

/**
 * Shared Puerto Rico regional camera contract.
 *
 * MapLibre consumes zoom/bounds while Cesium consumes physical heights and
 * orientation. These values intentionally describe equivalent product limits,
 * not exact cross-projection camera parity.
 */
export const REGIONAL_CAMERA_CONSTRAINTS = {
  center: [-66.35, 18.22] as [number, number],
  bounds: [
    [-73.0, 15.0],
    [-62.5, 21.5],
  ] as [[number, number], [number, number]],
  mapLibre: {
    minimumZoom: 7.4,
    maximumZoom: 19,
  },
  cesium: {
    initialHeightMeters: 450_000,
    minimumHeightMeters: 250,
    maximumHeightMeters: 1_050_000,
    headingDegrees: 0,
    pitchDegrees: -55,
  },
} as const;

export function clampRegionalCameraHeight(heightMeters: number): number {
  const { minimumHeightMeters, maximumHeightMeters } = REGIONAL_CAMERA_CONSTRAINTS.cesium;
  if (!Number.isFinite(heightMeters)) return REGIONAL_CAMERA_CONSTRAINTS.cesium.initialHeightMeters;
  return Math.min(maximumHeightMeters, Math.max(minimumHeightMeters, heightMeters));
}

// This center/zoom is independent of the gebco/terrain.py PR_LON_MIN/PR_LAT_MIN
// bounding envelope — the two currently have no shared source of truth for
// "where is Puerto Rico." Worth reconciling once a real analytical-domain
// registry exists; out of scope for this config move.
export const DEFAULT_REGIONAL_SCENE_CONFIG: SpatialSceneConfig = {
  basemapStyle: rasterStyle,
  basemapSourceId: BASEMAP_ID,
  initialView: {
    center: REGIONAL_CAMERA_CONSTRAINTS.center,
    zoom: 8.4,
  },
};
