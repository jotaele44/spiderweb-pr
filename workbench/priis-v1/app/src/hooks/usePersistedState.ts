import { useEffect, useState } from "react";

/**
 * Single key that records the schema version of all persisted state.
 * Bump this when the shape of ANY persisted value changes incompatibly
 * (call `clearStaleStorage` once at module load before any
 * `usePersistedState` runs).
 */
const VERSION_KEY = "priis_storage_version";

/**
 * Wipe every persisted key if the stored version doesn't match `current`.
 *
 * Called once at module load (NOT inside a component) so that the
 * subsequent `usePersistedState` lazy initialisers see a clean slate
 * when the schema has changed.
 *
 * `knownKeys` is the closed set we manage; we don't blanket-clear all of
 * localStorage because the host page may legitimately store other keys.
 */
export function clearStaleStorage(current: string, knownKeys: string[]): void {
  if (typeof localStorage === "undefined") return;
  if (localStorage.getItem(VERSION_KEY) === current) return;
  for (const k of knownKeys) localStorage.removeItem(k);
  localStorage.setItem(VERSION_KEY, current);
}

interface Options<T> {
  /** Custom deserialiser. Default: JSON.parse + identity. Must return a value
   * compatible with `T`; throw or return `undefined` to fall through to
   * `initial`. */
  parse?: (raw: string) => T | undefined;
  /** Custom serialiser. Default: JSON.stringify. */
  serialize?: (value: T) => string;
}

/**
 * Persist a piece of React state in `localStorage[key]`.
 *
 * The load happens in a **lazy useState initialiser**, which runs
 * synchronously during render BEFORE any effect. This is the only race-free
 * way to load saved state without the classic "save-on-change effect fires
 * on mount and wipes the saved value" bug.
 *
 * @example
 *   const [watchlist, setWatchlist] = usePersistedState<Selection[]>(
 *     "priis_watchlist", [],
 *   );
 */
export function usePersistedState<T>(
  key: string,
  initial: T,
  options: Options<T> = {},
): [T, React.Dispatch<React.SetStateAction<T>>] {
  const { parse, serialize = JSON.stringify } = options;

  const [value, setValue] = useState<T>(() => {
    if (typeof localStorage === "undefined") return initial;
    const raw = localStorage.getItem(key);
    if (raw === null) return initial;
    try {
      if (parse) {
        const parsed = parse(raw);
        return parsed === undefined ? initial : parsed;
      }
      return JSON.parse(raw) as T;
    } catch {
      // Corrupt JSON or parse rejection — drop it so we don't keep retrying.
      try {
        localStorage.removeItem(key);
      } catch {
        // ignore
      }
      return initial;
    }
  });

  useEffect(() => {
    if (typeof localStorage === "undefined") return;
    try {
      localStorage.setItem(key, serialize(value));
    } catch {
      // QuotaExceeded or storage disabled — silently drop, the in-memory
      // value remains correct.
    }
  }, [key, serialize, value]);

  return [value, setValue];
}
