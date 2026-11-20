import type * as maplibregl from "maplibre-gl";
import {
  DRAWN_STATUS_GROUPS,
  STATUS_GROUP_MEMBERS,
  statusGroup,
  type AccessPointFeature,
  type AccessPointRegistryId,
  type DrawnStatusGroup,
  type RegistryStatus,
} from "./accessPointsApi";

/**
 * MapLibre plumbing for the two access-point registries. Kept free of React.
 *
 * Each registry gets its own GeoJSON source and its own layers, so one can be
 * shown, filtered, fail or be removed without touching the other. Everything
 * is a GL circle layer; there are no DOM markers.
 *
 * Status is carried by shape, not only colour:
 *   verified     filled disc
 *   candidate    open ring (also UNDER_REVIEW)
 *   provisional  smaller, fainter, thinner open ring
 * A separate translucent halo is drawn only where a horizontal uncertainty is
 * stated. No halo means the uncertainty is unknown; it never means zero.
 *
 * Only records with registered point coordinates reach the map. A record with
 * no geometry is not given a position here under any circumstances.
 */

export const ACCESS_POINT_SOURCE_IDS: Record<AccessPointRegistryId, string> = {
  inland: "access-points-inland",
  offshore: "access-points-offshore",
};

export interface AccessPointLayerIds {
  halo: string;
  points: string;
  selected: string;
}

export function accessPointLayerIds(registry: AccessPointRegistryId): AccessPointLayerIds {
  const sourceId = ACCESS_POINT_SOURCE_IDS[registry];
  return {
    halo: `${sourceId}-uncertainty`,
    points: `${sourceId}-points`,
    selected: `${sourceId}-selected`,
  };
}

/** Map paint cannot read CSS variables; these mirror --fd-access-inland/offshore. */
export const ACCESS_POINT_COLORS: Record<AccessPointRegistryId, string> = {
  inland: "#b3541e",
  offshore: "#1b6f9c",
};

const SELECTED_COLOR = "#14181c";

// ── Splitting a registry into what is drawn and what is only listed ──────────

export type NotDrawnReason = "no-coordinates" | "non-point-geometry" | "retired";

export interface NotDrawnRecord {
  feature: AccessPointFeature;
  reason: NotDrawnReason;
}

export interface AccessPointMapFeature {
  type: "Feature";
  id: string;
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: {
    feature_id: string;
    status: RegistryStatus;
    feature_class: string;
    horizontal_uncertainty_m: number | null;
    horizontal_uncertainty_state: "STATED" | "UNKNOWN";
  };
}

export interface AccessPointMapData {
  type: "FeatureCollection";
  features: AccessPointMapFeature[];
}

export interface PartitionedFeatures {
  mapData: AccessPointMapData;
  notDrawn: NotDrawnRecord[];
}

/**
 * Decide, record by record, whether it may appear on the map. Rejected and
 * superseded records are listed rather than drawn, so a retired record cannot
 * be mistaken for a live one.
 */
export function partitionFeatures(features: readonly AccessPointFeature[]): PartitionedFeatures {
  const drawn: AccessPointMapFeature[] = [];
  const notDrawn: NotDrawnRecord[] = [];
  for (const feature of features) {
    const geometry = feature.geometry;
    if (geometry === null) {
      notDrawn.push({ feature, reason: "no-coordinates" });
    } else if (geometry.type !== "Point" || !("coordinates" in geometry) || !Array.isArray(geometry.coordinates)) {
      notDrawn.push({ feature, reason: "non-point-geometry" });
    } else if (statusGroup(feature.properties.status) === "retired") {
      notDrawn.push({ feature, reason: "retired" });
    } else {
      const [lng, lat] = geometry.coordinates as [number, number];
      drawn.push({
        type: "Feature",
        id: feature.id,
        geometry: { type: "Point", coordinates: [lng, lat] },
        properties: {
          feature_id: feature.properties.feature_id,
          status: feature.properties.status,
          feature_class: feature.properties.feature_class,
          horizontal_uncertainty_m: feature.properties.horizontal_uncertainty_m,
          horizontal_uncertainty_state: feature.properties.horizontal_uncertainty_state,
        },
      });
    }
  }
  return { mapData: { type: "FeatureCollection", features: drawn }, notDrawn };
}

// ── Expressions ──────────────────────────────────────────────────────────────

export function statusesForGroups(groups: Readonly<Record<DrawnStatusGroup, boolean>>): RegistryStatus[] {
  return DRAWN_STATUS_GROUPS.filter((group) => groups[group]).flatMap((group) => [...STATUS_GROUP_MEMBERS[group]]);
}

export function statusFilter(statuses: readonly RegistryStatus[]): maplibregl.FilterSpecification {
  return ["in", ["get", "status"], ["literal", [...statuses]]] as unknown as maplibregl.FilterSpecification;
}

function haloFilter(statuses: readonly RegistryStatus[]): maplibregl.FilterSpecification {
  return [
    "all",
    statusFilter(statuses),
    ["==", ["get", "horizontal_uncertainty_state"], "STATED"],
    [">", ["to-number", ["get", "horizontal_uncertainty_m"], 0], 0],
  ] as unknown as maplibregl.FilterSpecification;
}

function selectedFilter(featureId: string | null): maplibregl.FilterSpecification {
  return ["==", ["get", "feature_id"], featureId ?? ""] as unknown as maplibregl.FilterSpecification;
}

const EARTH_CIRCUMFERENCE_M = 40075016.686;
const TILE_SIZE_PX = 512;
const HALO_MAX_ZOOM = 24;

/** Screen pixels per ground metre at zoom 0 for a latitude (Web Mercator). */
export function pixelsPerMetreAtZoomZero(latitudeDeg: number): number {
  return TILE_SIZE_PX / (EARTH_CIRCUMFERENCE_M * Math.cos((latitudeDeg * Math.PI) / 180));
}

/** Mean latitude of the drawn points; the halo scale is evaluated there. */
export function referenceLatitude(data: AccessPointMapData, fallback = 18.2): number {
  if (data.features.length === 0) return fallback;
  return data.features.reduce((sum, feature) => sum + feature.geometry.coordinates[1], 0) / data.features.length;
}

/**
 * Halo radius in pixels that tracks the stated uncertainty in metres as the
 * map zooms. Scale is evaluated at one reference latitude per registry, so the
 * halo is an approximate ground radius, which the legend says in words.
 */
export function haloRadiusExpression(latitudeDeg: number): unknown[] {
  const atZero = pixelsPerMetreAtZoomZero(latitudeDeg);
  const metres = ["to-number", ["get", "horizontal_uncertainty_m"], 0];
  return [
    "interpolate",
    ["exponential", 2],
    ["zoom"],
    0,
    ["*", metres, atZero],
    HALO_MAX_ZOOM,
    ["*", metres, atZero * 2 ** HALO_MAX_ZOOM],
  ];
}

const byStatus = (verified: unknown, candidate: unknown, provisional: unknown): unknown[] => [
  "match",
  ["get", "status"],
  "VERIFIED",
  verified,
  "PROVISIONAL_DISCOVERY",
  provisional,
  candidate,
];

/** Paint for the symbol layer; exported so tests can assert shape-by-status. */
export function pointPaint(registry: AccessPointRegistryId): Record<string, unknown> {
  const color = ACCESS_POINT_COLORS[registry];
  return {
    "circle-color": color,
    // Filled only when verified. Candidate and provisional stay hollow.
    "circle-opacity": byStatus(1, 0, 0),
    "circle-radius": byStatus(6.5, 6, 3.5),
    "circle-stroke-color": byStatus("#ffffff", color, color),
    "circle-stroke-width": byStatus(1.5, 2.5, 1.25),
    "circle-stroke-opacity": byStatus(1, 1, 0.65),
  };
}

// ── Add / update / remove ────────────────────────────────────────────────────

/**
 * Id of the first label (symbol) layer, so access points sit above every fill,
 * line and raster overlay but below map labels.
 */
export function firstLabelLayerId(map: maplibregl.Map): string | undefined {
  const layers = map.getStyle()?.layers ?? [];
  return layers.find((layer) => layer.type === "symbol")?.id;
}

interface SettableSource {
  setData?: (data: AccessPointMapData) => void;
}

/**
 * Add the registry's source and layers, or update them in place when they are
 * already there. Safe to call repeatedly with new data or a new filter.
 */
export function applyAccessPointLayers(
  map: maplibregl.Map,
  registry: AccessPointRegistryId,
  data: AccessPointMapData,
  statuses: readonly RegistryStatus[],
  selectedId: string | null = null,
): void {
  const sourceId = ACCESS_POINT_SOURCE_IDS[registry];
  const ids = accessPointLayerIds(registry);
  const color = ACCESS_POINT_COLORS[registry];
  const haloRadius = haloRadiusExpression(referenceLatitude(data));

  const existing = map.getSource(sourceId) as SettableSource | undefined;
  if (existing) {
    existing.setData?.(data);
  } else {
    map.addSource(sourceId, { type: "geojson", data: data as unknown as GeoJSON.FeatureCollection });
  }

  const before = firstLabelLayerId(map);
  if (map.getLayer(ids.halo)) {
    map.setPaintProperty(ids.halo, "circle-radius", haloRadius as unknown as maplibregl.ExpressionSpecification);
  } else {
    map.addLayer(
      {
        id: ids.halo,
        type: "circle",
        source: sourceId,
        filter: haloFilter(statuses),
        paint: {
          "circle-color": color,
          "circle-opacity": 0.14,
          "circle-radius": haloRadius,
          "circle-stroke-color": color,
          "circle-stroke-width": 1,
          "circle-stroke-opacity": 0.35,
          "circle-pitch-alignment": "map",
        },
      } as unknown as maplibregl.LayerSpecification,
      before,
    );
  }
  if (!map.getLayer(ids.points)) {
    map.addLayer(
      {
        id: ids.points,
        type: "circle",
        source: sourceId,
        filter: statusFilter(statuses),
        paint: pointPaint(registry),
      } as unknown as maplibregl.LayerSpecification,
      before,
    );
  }
  if (!map.getLayer(ids.selected)) {
    map.addLayer(
      {
        id: ids.selected,
        type: "circle",
        source: sourceId,
        filter: selectedFilter(selectedId),
        paint: {
          "circle-radius": 11,
          "circle-opacity": 0,
          "circle-stroke-color": SELECTED_COLOR,
          "circle-stroke-width": 2,
        },
      } as unknown as maplibregl.LayerSpecification,
      before,
    );
  }
  setAccessPointStatusFilter(map, registry, statuses);
  setSelectedAccessPoint(map, registry, selectedId);
}

export function setAccessPointStatusFilter(
  map: maplibregl.Map,
  registry: AccessPointRegistryId,
  statuses: readonly RegistryStatus[],
): void {
  const ids = accessPointLayerIds(registry);
  if (map.getLayer(ids.points)) map.setFilter(ids.points, statusFilter(statuses));
  if (map.getLayer(ids.halo)) map.setFilter(ids.halo, haloFilter(statuses));
}

export function setSelectedAccessPoint(
  map: maplibregl.Map,
  registry: AccessPointRegistryId,
  featureId: string | null,
): void {
  const ids = accessPointLayerIds(registry);
  if (map.getLayer(ids.selected)) map.setFilter(ids.selected, selectedFilter(featureId));
}

/** Remove one registry's layers and source. A map with no style is left alone. */
export function removeAccessPointLayers(map: maplibregl.Map, registry: AccessPointRegistryId): void {
  if (!map.getStyle()) return;
  const sourceId = ACCESS_POINT_SOURCE_IDS[registry];
  const ids = accessPointLayerIds(registry);
  [ids.selected, ids.points, ids.halo].forEach((id) => {
    if (map.getLayer(id)) map.removeLayer(id);
  });
  if (map.getSource(sourceId)) map.removeSource(sourceId);
}
