import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// Use this test window's storage rather than Node's optional Web Storage
// globals, which may be unavailable without a --localstorage-file argument.
function testStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() { return values.size; },
    clear: () => values.clear(),
    getItem: (key) => values.get(String(key)) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => { values.delete(String(key)); },
    setItem: (key, value) => { values.set(String(key), String(value)); },
  };
}
vi.stubGlobal("localStorage", testStorage());
vi.stubGlobal("sessionStorage", testStorage());

// Testing Library only auto-registers cleanup when vitest globals are on. This
// harness imports describe/it/expect explicitly (see vitest.config.ts), so the
// unmount has to be wired up here or mounted trees leak between test files.
afterEach(cleanup);
