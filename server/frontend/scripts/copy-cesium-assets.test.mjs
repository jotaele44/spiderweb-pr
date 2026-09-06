import assert from "node:assert/strict";
import {
  existsSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { copyCesiumAssets } from "./copy-cesium-assets.mjs";

const directories = ["Workers", "ThirdParty", "Assets", "Widgets"];

function fixtureRoot() {
  return mkdtempSync(path.join(os.tmpdir(), "spiderweb-cesium-"));
}

test("copies every required Cesium directory after complete preflight", () => {
  const root = fixtureRoot();
  try {
    const source = path.join(root, "node_modules", "cesium", "Build", "Cesium");
    for (const directory of directories) {
      const folder = path.join(source, directory);
      mkdirSync(folder, { recursive: true });
      writeFileSync(path.join(folder, "fixture.txt"), directory, "utf8");
    }

    const result = copyCesiumAssets(root);
    assert.deepEqual(result.directories, directories);
    for (const directory of directories) {
      const copied = path.join(root, "public", "cesium", directory, "fixture.txt");
      assert.equal(readFileSync(copied, "utf8"), directory);
    }
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("fails before creating a partial destination when a directory is missing", () => {
  const root = fixtureRoot();
  try {
    const source = path.join(root, "node_modules", "cesium", "Build", "Cesium");
    for (const directory of directories.slice(0, -1)) {
      mkdirSync(path.join(source, directory), { recursive: true });
    }

    assert.throws(() => copyCesiumAssets(root), /missing: Widgets/);
    assert.equal(existsSync(path.join(root, "public", "cesium")), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("fails when the installed Cesium build is absent", () => {
  const root = fixtureRoot();
  try {
    assert.throws(() => copyCesiumAssets(root), /Cesium build not found/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
