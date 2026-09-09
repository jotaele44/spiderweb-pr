#!/usr/bin/env node
import {
  cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync,
  renameSync, rmSync, statSync,
} from "node:fs";
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
    (directory) => {
      const source = path.join(cesiumBuild, directory);
      return !existsSync(source) || !statSync(source).isDirectory() ||
        readdirSync(source).length === 0;
    },
  );
  if (missing.length > 0) {
    throw new Error(
      `[copy-cesium-assets] incomplete Cesium build; missing: ${missing.join(", ")}`,
    );
  }

  mkdirSync(path.dirname(destination), { recursive: true });
  const transaction = mkdtempSync(path.join(path.dirname(destination), ".cesium-copy-"));
  const staged = path.join(transaction, "staged");
  const previous = path.join(transaction, "previous");
  let backedUp = false;
  let published = false;
  try {
    mkdirSync(staged);
    for (const directory of staticDirectories) {
      cpSync(path.join(cesiumBuild, directory), path.join(staged, directory), {
        recursive: true,
      });
    }
    if (existsSync(destination)) {
      renameSync(destination, previous);
      backedUp = true;
    }
    renameSync(staged, destination);
    published = true;
  } catch (error) {
    if (backedUp && !published) {
      // Preserve the backup if restoration itself fails; never delete the
      // only complete copy merely to clean up a failed transaction.
      try {
        renameSync(previous, destination);
        backedUp = false;
      } catch (restoreError) {
        throw new AggregateError([error, restoreError],
          `Cesium copy failed; previous assets retained at ${previous}`);
      }
    }
    throw error;
  } finally {
    if (published || !backedUp) rmSync(transaction, { recursive: true, force: true });
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
