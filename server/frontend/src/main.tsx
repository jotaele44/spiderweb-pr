import React from "react";
import ReactDOM from "react-dom/client";
import "maplibre-gl/dist/maplibre-gl.css";

// Self-hosted fonts (bundled by Vite — no runtime network request). Latin subset
// only; the UI is English-language, so other subsets would just bloat the build.
import "@fontsource/public-sans/latin-400.css";
import "@fontsource/public-sans/latin-500.css";
import "@fontsource/public-sans/latin-600.css";
import "@fontsource/public-sans/latin-700.css";
import "@fontsource/jetbrains-mono/latin-400.css";
import "@fontsource/jetbrains-mono/latin-500.css";
import "@fontsource/jetbrains-mono/latin-600.css";
import "@fontsource/source-serif-4/latin-400.css";
import "@fontsource/source-serif-4/latin-500.css";
import "@fontsource/source-serif-4/latin-600.css";

import "./styles/federation.css";
import "./styles/app.css";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { THEME_STORAGE_KEY, resolveInitialTheme } from "./theme";

document.documentElement.dataset.repo = "spiderweb-pr";
// Set the initial theme before first paint to avoid a flash of the wrong theme.
document.documentElement.dataset.theme = resolveInitialTheme(
  localStorage.getItem(THEME_STORAGE_KEY),
);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {/* Outer boundary catches throws in the chrome itself (command bar, rail,
        inspector, timeline) — the per-module boundary lives inside App. */}
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
