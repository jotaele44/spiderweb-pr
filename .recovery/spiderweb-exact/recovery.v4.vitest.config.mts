import { defineConfig } from "vitest/config";

export default defineConfig({
  esbuild: {
    jsx: "automatic",
    jsxImportSource: "react",
  },
  test: {
    globals: true,
    environment: "jsdom",
    include: ["helpers/**/*.spec.ts", "helpers/**/*.spec.tsx"],
    exclude: ["helpers/useDebounce.spec.tsx"],
    setupFiles: ["./recovery.vitest.setup.mjs"],
    restoreMocks: true,
    clearMocks: true,
  },
});
