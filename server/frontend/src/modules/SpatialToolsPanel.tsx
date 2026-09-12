import { useEffect, useState } from "react";
import { SpatialToolsPanel as LegacyPanel, useSpatialTools as useLegacyTools } from "./SpatialToolsLegacy";
import { AoiMapWorkbench } from "./AoiMapWorkbench";
import type { AoiMode } from "./aoiContract";
export { pointCandidateSet, measureFeatureCollection, bufferPointCandidates, nearestPointCandidate } from "./SpatialToolsLegacy";
export type { ToolMode } from "./SpatialToolsLegacy";

/** Extend the existing SpatialIntelligence mount without replacing its tools. */
export function useSpatialTools(options: Parameters<typeof useLegacyTools>[0]) {
  const legacy = useLegacyTools(options);
  const [aoiMode, setAoiModeState] = useState<AoiMode>("idle");
  useEffect(() => {
    options.interactionLockRef.current = legacy.mode !== "off" || aoiMode !== "idle";
    return () => { options.interactionLockRef.current = false; };
  }, [options.interactionLockRef, legacy.mode, aoiMode]);
  const setAoiMode = (mode: AoiMode) => {
    if (mode !== "idle") legacy.setMode("off");
    setAoiModeState(mode);
  };
  const setMode = (mode: typeof legacy.mode) => {
    setAoiModeState("idle");
    legacy.setMode(mode);
  };
  return { ...legacy, setMode, aoiMode, setAoiMode, mapRef: options.mapRef, mapReady: options.mapReady };
}
export function SpatialToolsPanel(state: ReturnType<typeof useSpatialTools>) {
  return <>
    <LegacyPanel {...state} />
    <AoiMapWorkbench mapRef={state.mapRef} mapReady={state.mapReady} mode={state.aoiMode} setMode={state.setAoiMode} />
  </>;
}
