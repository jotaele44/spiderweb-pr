#!/usr/bin/env node
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const appRoot = path.resolve(fileURLToPath(new URL(".", import.meta.url)), "..");
const cesiumBuild = path.join(appRoot, "node_modules", "cesium", "Build", "Cesium");
const destination = path.join(appRoot, "public", "cesium");
const staticDirectories = ["Workers", "ThirdParty", "Assets", "Widgets"];

if (!existsSync(cesiumBuild)) {
  console.warn(`[copy-cesium-assets] ${cesiumBuild} not found; skipping`);
  process.exit(0);
}

mkdirSync(destination, { recursive: true });
for (const directory of staticDirectories) {
  const source = path.join(cesiumBuild, directory);
  if (!existsSync(source)) {
    console.warn(`[copy-cesium-assets] ${source} missing; skipping`);
    continue;
  }
  cpSync(source, path.join(destination, directory), { recursive: true });
}

console.log(`[copy-cesium-assets] copied ${staticDirectories.join(", ")} to public/cesium`);
