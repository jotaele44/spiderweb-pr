import { useCallback, useEffect, useMemo, useState } from "react";
import type * as maplibregl from "maplibre-gl";
import {
  ACCESS_POINT_REGISTRIES,
  DRAWN_STATUS_GROUPS,
  errorMessage,
  fetchAccessPointEvidence,
  fetchRegistrySnapshot,
  fetchSourceCoverage,
  type AccessPointEvidence,
  type AccessPointFeature,
  type AccessPointRegistryId,
  type AccessPointSourceCoverage,
  type DrawnStatusGroup,
  type RegistrySnapshot,
} from "./accessPointsApi";
import {
  accessPointLayerIds,
  applyAccessPointLayers,
  partitionFeatures,
  removeAccessPointLayers,
  statusesForGroups,
  type NotDrawnRecord,
} from "./accessPointLayers";

/**
 * "loaded" is reached only after the map itself reports the layer drawn.
 * A successful fetch alone stops at "source-ready".
 */
export type RegistryLoadState = "off" | "loading" | "source-ready" | "loaded" | "error";

export interface RegistryView {
  registry: AccessPointRegistryId;
  enabled: boolean;
  state: RegistryLoadState;
  error: string | null;
  snapshot: RegistrySnapshot | null;
  drawnCount: number;
  notDrawn: NotDrawnRecord[];
}

export interface AccessPointSelection {
  registry: AccessPointRegistryId;
  featureId: string;
}

export type EvidenceState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; evidence: AccessPointEvidence }
  | { status: "error"; message: string };

export type CoverageState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; coverage: AccessPointSourceCoverage }
  | { status: "error"; message: string };

type StatusGroups = Record<DrawnStatusGroup, boolean>;
const ALL_GROUPS: StatusGroups = { verified: true, candidate: true, provisional: true };

interface RegistryOptions {
  registry: AccessPointRegistryId;
  mapRef: React.MutableRefObject<maplibregl.Map | null>;
  ready: boolean;
  groups: StatusGroups;
  selectedId: string | null;
  onSelect: (selection: AccessPointSelection) => void;
}

type FetchResult =
  | { status: "ready"; snapshot: RegistrySnapshot }
  | { status: "error"; message: string };

/** One registry: its own fetch, its own layers, its own failure. */
function useRegistryLayer(opts: RegistryOptions) {
  const { registry, mapRef, ready, groups, selectedId, onSelect } = opts;
  const [enabled, setEnabled] = useState(false);
  // Set only from asynchronous callbacks; the load state is derived below.
  const [result, setResult] = useState<FetchResult | null>(null);
  const [drawn, setDrawn] = useState(false);

  const toggle = useCallback(() => {
    setResult(null);
    setDrawn(false);
    setEnabled((on) => !on);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    fetchRegistrySnapshot(registry)
      .then((snapshot) => {
        if (!cancelled) setResult({ status: "ready", snapshot });
      })
      .catch((reason: unknown) => {
        if (!cancelled) setResult({ status: "error", message: errorMessage(reason) });
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, registry]);

  const snapshot = enabled && result?.status === "ready" ? result.snapshot : null;
  const error = enabled && result?.status === "error" ? result.message : null;
  const state: RegistryLoadState = !enabled
    ? "off"
    : result === null
      ? "loading"
      : result.status === "error"
        ? "error"
        : drawn
          ? "loaded"
          : "source-ready";

  const partition = useMemo(() => partitionFeatures(snapshot?.features ?? []), [snapshot]);
  const statuses = useMemo(() => statusesForGroups(groups), [groups]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !enabled || !snapshot) return;
    let cancelled = false;
    const apply = () => {
      if (cancelled) return;
      applyAccessPointLayers(map, registry, partition.mapData, statuses, selectedId);
      void map.once("idle", () => {
        if (!cancelled) setDrawn(true);
      });
    };
    if (map.isStyleLoaded()) apply();
    else void map.once("styledata", apply);
    return () => {
      cancelled = true;
    };
  }, [enabled, mapRef, partition, ready, registry, selectedId, snapshot, statuses]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !enabled) return;
    const layerId = accessPointLayerIds(registry).points;
    const onClick = (event: maplibregl.MapLayerMouseEvent) => {
      const id: unknown = event.features?.[0]?.properties?.feature_id;
      if (typeof id === "string") onSelect({ registry, featureId: id });
    };
    map.on("click", layerId, onClick);
    return () => {
      map.off("click", layerId, onClick);
    };
  }, [enabled, mapRef, onSelect, ready, registry]);

  useEffect(() => {
    const map = mapRef.current;
    if (enabled || !map) return;
    removeAccessPointLayers(map, registry);
  }, [enabled, mapRef, registry]);

  useEffect(() => {
    const map = mapRef.current;
    return () => {
      if (map) removeAccessPointLayers(map, registry);
    };
  }, [mapRef, registry]);

  const view: RegistryView = {
    registry,
    enabled,
    state,
    error,
    snapshot,
    drawnCount: partition.mapData.features.length,
    notDrawn: partition.notDrawn,
  };
  return { view, toggle };
}

/**
 * State for the access-point layer group. The two registries are loaded,
 * drawn and reported independently: one failing never hides the other.
 */
export function useAccessPointsController(opts: {
  mapRef: React.MutableRefObject<maplibregl.Map | null>;
  /** True once the MapLibre map is usable (false in 3D mode). */
  ready: boolean;
}) {
  const { mapRef, ready } = opts;
  const [groups, setGroups] = useState<StatusGroups>(ALL_GROUPS);
  const [selection, setSelection] = useState<AccessPointSelection | null>(null);
  const [evidenceResult, setEvidenceResult] = useState<{ key: string; state: EvidenceState } | null>(null);
  const [coverageRegistry, setCoverageRegistry] = useState<AccessPointRegistryId | null>(null);
  const [coverageResult, setCoverageResult] = useState<{ key: string; state: CoverageState } | null>(null);

  const onSelect = useCallback((next: AccessPointSelection) => setSelection(next), []);
  const inland = useRegistryLayer({
    registry: "inland",
    mapRef,
    ready,
    groups,
    selectedId: selection?.registry === "inland" ? selection.featureId : null,
    onSelect,
  });
  const offshore = useRegistryLayer({
    registry: "offshore",
    mapRef,
    ready,
    groups,
    selectedId: selection?.registry === "offshore" ? selection.featureId : null,
    onSelect,
  });

  const selectionKey = selection ? `${selection.registry}/${selection.featureId}` : null;
  useEffect(() => {
    if (!selection) return;
    let cancelled = false;
    const key = `${selection.registry}/${selection.featureId}`;
    fetchAccessPointEvidence(selection.registry, selection.featureId)
      .then((result) => {
        if (!cancelled) setEvidenceResult({ key, state: { status: "ready", evidence: result } });
      })
      .catch((reason: unknown) => {
        if (!cancelled) setEvidenceResult({ key, state: { status: "error", message: errorMessage(reason) } });
      });
    return () => {
      cancelled = true;
    };
  }, [selection]);
  const evidence: EvidenceState =
    selectionKey === null
      ? { status: "idle" }
      : evidenceResult?.key === selectionKey
        ? evidenceResult.state
        : { status: "loading" };

  useEffect(() => {
    if (!coverageRegistry) return;
    let cancelled = false;
    const key = coverageRegistry;
    fetchSourceCoverage(coverageRegistry)
      .then((result) => {
        if (!cancelled) setCoverageResult({ key, state: { status: "ready", coverage: result } });
      })
      .catch((reason: unknown) => {
        if (!cancelled) setCoverageResult({ key, state: { status: "error", message: errorMessage(reason) } });
      });
    return () => {
      cancelled = true;
    };
  }, [coverageRegistry]);
  const coverage: CoverageState =
    coverageRegistry === null
      ? { status: "idle" }
      : coverageResult?.key === coverageRegistry
        ? coverageResult.state
        : { status: "loading" };

  const views: Record<AccessPointRegistryId, RegistryView> = { inland: inland.view, offshore: offshore.view };
  const selectedFeature: AccessPointFeature | null = selection
    ? (views[selection.registry].snapshot?.features.find((f) => f.id === selection.featureId) ?? null)
    : null;

  const toggleRegistry = useCallback(
    (registry: AccessPointRegistryId) => {
      (registry === "inland" ? inland.toggle : offshore.toggle)();
    },
    [inland.toggle, offshore.toggle],
  );
  const toggleGroup = useCallback(
    (group: DrawnStatusGroup) => setGroups((current) => ({ ...current, [group]: !current[group] })),
    [],
  );

  return {
    registries: ACCESS_POINT_REGISTRIES.map((registry) => views[registry]),
    groups,
    statusGroups: DRAWN_STATUS_GROUPS,
    toggleRegistry,
    toggleGroup,
    selection,
    selectedFeature,
    select: setSelection,
    evidence,
    coverageRegistry,
    setCoverageRegistry,
    coverage,
  };
}

export type AccessPointsControllerState = ReturnType<typeof useAccessPointsController>;
