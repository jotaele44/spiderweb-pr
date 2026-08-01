import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Modelled on the sibling producers' harnesses, but this frontend differs from
// them in ways that change the setup, so the differences are recorded here.
//
// Deliberately a local file rather than a rendered federation template: a
// registered template target a repo lacks counts as drift, so templating the
// harness would mark every frontend drifted until the last one had it.
//
// Separate from vite.config.ts rather than a `test` key inside it, matching the
// siblings — the build config stays about building.
//
// jsdom rather than node. The pure modules here (schemas/priis.ts,
// export/evidenceBrief.ts, adapters/queryAdapter.ts) would run happily in node,
// but export/csvExport.ts reaches the DOM through Blob, URL.createObjectURL and
// a synthetic anchor click, and its RFC-4180 escaping is only reachable through
// that path — escapeCell and toCsv are module-private. Testing the escaping
// without jsdom would mean exporting them purely to make them testable, which
// is a worse trade than one dev dependency.
//
// Tests are co-located under src/ on purpose. eslint's type-checked block globs
// src/**/*.{ts,tsx} and tsconfig.app.json includes only "src", so a top-level
// tests/ directory would be linted by neither and type-checked by neither — a
// gate reporting success over files it never looked at. Co-locating means
// `npm run lint` and `npm run typecheck` both cover the tests, which is also why
// they import describe/it/expect explicitly instead of relying on globals: tsc
// would reject the bare identifiers.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
