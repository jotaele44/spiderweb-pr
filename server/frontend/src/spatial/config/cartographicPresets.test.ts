import { describe, expect, it } from "vitest";
import { NEUTRAL_PRESET, resolvePresets, type Preset } from "./cartographicPresets";

const known = ["municipios", "barrios"];
const base: Preset = { id: "base", version: "1", layers: { municipios: { priority: 4, opacity: 0.8 } } };
const modifier: Preset = { id: "modifier", version: "1", layers: { municipios: { opacity: 0.2 } } };

describe("laboratory preset resolver", () => {
  it("preserves defaults for zero mounts and neutral mode", () => {
    expect(resolvePresets(known, []).layers).toEqual({});
    expect(resolvePresets(known, [NEUTRAL_PRESET]).layers).toEqual({});
  });
  it("resolves properties independently with provenance", () => {
    const result = resolvePresets(known, [base, modifier]);
    expect(result.layers.municipios).toEqual({ priority: 4, opacity: 0.2 });
    expect(result.trace.municipios).toEqual({ priority: "base@1", opacity: "modifier@1" });
    expect(resolvePresets(known, [base, modifier])).toEqual(result);
  });
  it("does not mutate inputs", () => {
    const before = JSON.stringify(base);
    resolvePresets(known, [base, modifier]);
    expect(JSON.stringify(base)).toBe(before);
  });
  it("rejects unknown layers and duplicate presets", () => {
    expect(() => resolvePresets([], [base])).toThrow();
    expect(() => resolvePresets(known, [base, base])).toThrow();
  });
  it("rejects invalid numeric values", () => {
    expect(() => resolvePresets(known, [{ ...base, layers: { municipios: { opacity: NaN } } }])).toThrow();
    expect(() => resolvePresets(known, [{ ...base, layers: { municipios: { opacity: 2 } } }])).toThrow();
  });
  it("rejects geometry mutation fields", () => {
    const invalid = { ...base, layers: { municipios: { opacity: 1, geometry: {} } } };
    expect(() => resolvePresets(known, [invalid])).toThrow();
  });
  it("enforces hidden priority", () => {
    expect(resolvePresets(known, [{ ...base, layers: { municipios: { priority: 0, visible: true } } }]).layers.municipios.visible).toBe(false);
  });
});
