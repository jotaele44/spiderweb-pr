import globals from "globals";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import pluginUnusedImports from "eslint-plugin-unused-imports";

// This package is the odd one out in the federation. The other five producer
// frontends share a single JSX-flavoured eslint config, rendered from
// thehub-pr/federation-templates — but that one globs src/components/**,
// src/pages/** and src/Layout.jsx at .{js,mjs,cjs,jsx}, and this frontend is
// TypeScript with no pages directory, no Layout, and zero .jsx files. Rendering
// it here would lint nothing at all and report a passing gate over an empty file
// list, so this config is deliberately local rather than templated.
//
// Rules are the non-type-checked set on purpose. tsconfig.json here sets
// "strict": false, so the type-aware presets (as used by workbench/priis-v1/app)
// would report a large backlog on a package that has never been linted — a gate
// that is red on arrival gets disabled rather than fixed. The type-aware rules
// are the natural next step once `strict` is on.
export default tseslint.config(
  { ignores: ["dist", "node_modules", "src/lib/snapshot.json"] },
  {
    files: ["src/**/*.{ts,tsx}"],
    extends: [...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "unused-imports": pluginUnusedImports,
    },
    rules: {
      // TypeScript already resolves identifiers, so no-undef is redundant here —
      // unlike the JSX config, where it is the rule that catches a component
      // referencing something it forgot to import.
      "no-undef": "off",
      // Defer to unused-imports so an unused import is an error while an unused
      // local is a warning, matching the other five frontends' behaviour.
      "@typescript-eslint/no-unused-vars": "off",
      "unused-imports/no-unused-imports": "error",
      "unused-imports/no-unused-vars": [
        "warn",
        {
          vars: "all",
          varsIgnorePattern: "^_",
          args: "after-used",
          argsIgnorePattern: "^_",
        },
      ],
      // Warn, not error. The three existing `any`s here are deliberate
      // placeholders — a not-yet-unioned `selected` entity in the zustand
      // store and GeoJSON `features` — and retyping them means changing
      // their consumers, which is a code change rather than the CI gate this
      // is. Visible in the log, does not fail the build; tighten it with
      // `strict` when the type-aware presets go on.
      "@typescript-eslint/no-explicit-any": "warn",
      "react-hooks/rules-of-hooks": "error",
    },
  },
);
