/**
 * Shareable map state in the URL fragment.
 *
 * The app has no router, so the fragment is free. Format (every key optional):
 *
 *   #map=15.50/18.46550/-66.11670&eri=pre_event_2022_cb2201a&op=0.8&cmp=maria_20170924b&fp=1&base=0
 *
 * `map` is zoom/lat/lng. Unknown keys are preserved untouched so another
 * feature can use the fragment later without this module erasing its state.
 */

export interface MapViewState {
  view?: { zoom: number; lat: number; lng: number };
  /** Imagery dataset id shown on the map. */
  imagery?: string;
  /** Imagery opacity, 0–1. */
  opacity?: number;
  /** Dataset id on the right side of the swipe comparison. */
  compare?: string;
  footprints?: boolean;
  /** False when the base map is hidden. */
  basemap?: boolean;
}

const OWN_KEYS = ["map", "eri", "op", "cmp", "fp", "base"] as const;
const ID_RE = /^[a-z][a-z0-9_]*$/;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function parseViewHash(hash: string): MapViewState {
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  const state: MapViewState = {};

  const map = params.get("map");
  if (map) {
    const [zoom, lat, lng] = map.split("/").map(Number);
    if ([zoom, lat, lng].every(Number.isFinite) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180) {
      state.view = { zoom: clamp(zoom, 0, 24), lat, lng };
    }
  }
  const imagery = params.get("eri");
  if (imagery && ID_RE.test(imagery)) state.imagery = imagery;
  const compare = params.get("cmp");
  if (compare && ID_RE.test(compare)) state.compare = compare;
  const opacity = params.get("op");
  if (opacity !== null && opacity !== "" && Number.isFinite(Number(opacity))) {
    state.opacity = clamp(Number(opacity), 0, 1);
  }
  const footprints = params.get("fp");
  if (footprints === "0" || footprints === "1") state.footprints = footprints === "1";
  const basemap = params.get("base");
  if (basemap === "0" || basemap === "1") state.basemap = basemap === "1";
  return state;
}

export function formatViewHash(state: MapViewState, currentHash = ""): string {
  const params = new URLSearchParams(currentHash.replace(/^#/, ""));
  OWN_KEYS.forEach((key) => params.delete(key));
  const own: string[] = [];
  if (state.view) {
    const { zoom, lat, lng } = state.view;
    own.push(`map=${zoom.toFixed(2)}/${lat.toFixed(5)}/${lng.toFixed(5)}`);
  }
  if (state.imagery) own.push(`eri=${state.imagery}`);
  if (state.imagery && state.opacity !== undefined && state.opacity < 1) {
    own.push(`op=${Number(state.opacity.toFixed(2))}`);
  }
  if (state.imagery && state.compare) own.push(`cmp=${state.compare}`);
  if (state.imagery && state.footprints === false) own.push("fp=0");
  if (state.basemap === false) own.push("base=0");
  const rest = params.toString();
  const body = [...own, ...(rest ? [rest] : [])].join("&");
  return body ? `#${body}` : "";
}
