export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "spiderweb_theme";

/**
 * Resolve the theme to use at startup: an explicit stored choice wins, otherwise
 * fall back to the OS `prefers-color-scheme` (defaulting to dark, the workbench's
 * operational default).
 */
export function resolveInitialTheme(stored: string | null): Theme {
  if (stored === "light" || stored === "dark") return stored;
  if (typeof window !== "undefined" && window.matchMedia) {
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  return "dark";
}
