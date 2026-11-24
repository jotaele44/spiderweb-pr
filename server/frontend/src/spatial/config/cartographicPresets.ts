/** FAWS laboratory resolver. Display intent only; no geometry or renderer mutation. */
export const CONTRACT_VERSION = "spiderweb-cartographic-preset/0.1" as const;
export type Priority = 0 | 1 | 2 | 3 | 4 | 5;
export interface VisualPatch {
  priority?: Priority;
  opacity?: number;
  visible?: boolean;
}
export interface Preset {
  id: string;
  version: string;
  layers: Record<string, VisualPatch>;
}
export const NEUTRAL_PRESET: Preset = {
  id: "spiderweb.neutral", version: "0.1.0", layers: {},
};
const fields = ["priority", "opacity", "visible"] as const;

/** Ordered low-to-high precedence. Layer identities supplied by trusted catalog.
 * An empty stack is identity: existing renderer defaults remain untouched.
 * Mandatory attribution and provenance are outside this override surface.
 */
export function resolvePresets(
  knownLayers: readonly string[],
  stack: readonly Preset[],
): { contractVersion: typeof CONTRACT_VERSION; layers: Record<string, VisualPatch>; trace: Record<string, Record<string, string>> } {
  const known = new Set(knownLayers);
  const layers: Record<string, VisualPatch> = Object.create(null);
  const trace: Record<string, Record<string, string>> = Object.create(null);
  const seen = new Set<string>();
  for (const preset of stack) {
    if (!preset.id || !preset.version || seen.has(preset.id)) throw new Error("invalid or duplicate preset");
    seen.add(preset.id);
    for (const id of Object.keys(preset.layers).sort()) {
      if (!known.has(id) || !/^[a-z0-9_]+$/.test(id)) throw new Error("unknown or invalid layer");
      const patch = preset.layers[id];
      if (!patch || typeof patch !== "object" || Array.isArray(patch)) throw new Error("invalid patch");
      for (const key of Object.keys(patch)) {
        if (!(fields as readonly string[]).includes(key)) throw new Error("unsupported visual property");
      }
      const target = layers[id] ?? (layers[id] = {});
      const sources = trace[id] ?? (trace[id] = Object.create(null));
      for (const key of fields) {
        if (!Object.prototype.hasOwnProperty.call(patch, key)) continue;
        const value = patch[key];
        if (key === "priority") {
          if (typeof value !== "number" || !Number.isInteger(value) || value < 0 || value > 5) throw new Error("invalid priority");
          target.priority = value as Priority;
        } else if (key === "opacity") {
          if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) throw new Error("invalid opacity");
          target.opacity = value;
        } else {
          if (typeof value !== "boolean") throw new Error("invalid visibility");
          target.visible = value;
        }
        sources[key] = preset.id + "@" + preset.version;
      }
    }
  }
  // Hidden priority is a hard display-intent constraint until priority is raised.
  for (const id of Object.keys(layers)) {
    if (layers[id].priority === 0) {
      layers[id].visible = false;
      trace[id].visible = trace[id].priority + ":priority-zero";
    }
  }
  return { contractVersion: CONTRACT_VERSION, layers, trace };
}
