#!/usr/bin/env node
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const scriptPath = fileURLToPath(import.meta.url);
const defaultAppRoot = path.resolve(path.dirname(scriptPath), "..");
const staticDirectories = ["Workers", "ThirdParty", "Assets", "Widgets"];

export function copyCesiumAssets(appRoot = defaultAppRoot) {
  const cesiumBuild = path.join(appRoot, "node_modules", "cesium", "Build", "Cesium");
  const destination = path.join(appRoot, "public", "cesium");

  if (!existsSync(cesiumBuild)) {
    throw new Error(`[copy-cesium-assets] Cesium build not found: ${cesiumBuild}`);
  }

  const missing = staticDirectories.filter(
    (directory) => !existsSync(path.join(cesiumBuild, directory)),
  );
  if (missing.length > 0) {
    throw new Error(
      `[copy-cesium-assets] incomplete Cesium build; missing: ${missing.join(", ")}`,
    );
  }

  mkdirSync(destination, { recursive: true });
  for (const directory of staticDirectories) {
    cpSync(path.join(cesiumBuild, directory), path.join(destination, directory), {
      recursive: true,
    });
  }

  return {
    source: cesiumBuild,
    destination,
    directories: [...staticDirectories],
  };
}

const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : null;
if (invokedPath === scriptPath) {
  try {
    const result = copyCesiumAssets();
    console.log(
      `[copy-cesium-assets] copied ${result.directories.join(", ")} to ${result.destination}`,
    );
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
