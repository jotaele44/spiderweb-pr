#!/usr/bin/env bash
set -euo pipefail
ROOT="$RUNNER_TEMP/recovered"
ARCHIVE="$RUNNER_TEMP/spiderweb_exact.tar.gz"
rm -rf "$ROOT"
mkdir -p "$ROOT"

cat .recovery/spiderweb-exact/part-000     .recovery/spiderweb-exact/part-001     .recovery/spiderweb-exact/part-002     .recovery/spiderweb-exact/part-003 > "$ARCHIVE"

echo "b5e8c8ce51d221819d4f0040bcde5eeb984769cab2fd3165cad7082802723815  $ARCHIVE" | sha256sum -c -
tar -xzf "$ARCHIVE" -C "$ROOT"

python - <<'PY'
from pathlib import Path
import hashlib, os
root = Path(os.environ["RUNNER_TEMP"]) / "recovered"
manifest = Path(".recovery/spiderweb-exact/member_manifest.txt")
expected = {}
for line in manifest.read_text().splitlines():
    if not line.strip(): continue
    sha, size, path = line.split("  ", 2)
    expected[path] = (int(size), sha)
actual = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
if set(actual) != set(expected):
    raise SystemExit("base member-set mismatch")
for rel in actual:
    data=(root/rel).read_bytes()
    size,sha=expected[rel]
    if len(data)!=size or hashlib.sha256(data).hexdigest()!=sha:
        raise SystemExit(f"base member mismatch: {rel}")
if len(actual)!=272:
    raise SystemExit(f"expected 272 base files, got {len(actual)}")
print("BASE_EXACT_MEMBER_VERIFICATION=PASS")
print("BASE_RECOVERED_FILE_COUNT=272")
PY

mkdir -p "$ROOT/helpers" "$ROOT/components"
cp .reconstruction/spiderweb-forward-v1/helpers/spatialDatasetPipeline.tsx "$ROOT/helpers/spatialDatasetPipeline.tsx"
cp .reconstruction/spiderweb-forward-v1/helpers/spatialDatasetPipeline.spec.tsx "$ROOT/helpers/spatialDatasetPipeline.spec.tsx"\ncp .reconstruction/spiderweb-forward-v1/helpers/spatialSourceEquivalence.tsx "$ROOT/helpers/spatialSourceEquivalence.tsx"\ncp .reconstruction/spiderweb-forward-v1/helpers/spatialSourceEquivalence.spec.tsx "$ROOT/helpers/spatialSourceEquivalence.spec.tsx"
cp .reconstruction/spiderweb-forward-v1/components/SpatialDatasetIntakePanel.tsx "$ROOT/components/SpatialDatasetIntakePanel.tsx"
cp .reconstruction/spiderweb-forward-v1/components/SpatialDatasetIntakePanel.module.css "$ROOT/components/SpatialDatasetIntakePanel.module.css"
cp .reconstruction/spiderweb-forward-v1/components/SpatialAnalysisWorkbench.tsx "$ROOT/components/SpatialAnalysisWorkbench.tsx"

cd "$ROOT"
cp package.json package.original.json
export NPM_CONFIG_LEGACY_PEER_DEPS=true
npm install --no-audit --no-fund --ignore-scripts
npm install --save-dev --no-audit --no-fund --ignore-scripts   vitest@3.2.4 jsdom@26.1.0 @testing-library/react@16.2.0 @testing-library/dom@10.4.1

cat > recovery.vitest.config.mts <<'EOF'
import { defineConfig } from "vitest/config";
export default defineConfig({
  esbuild: { jsx: "automatic", jsxImportSource: "react" },
  test: {
    globals: true,
    environment: "jsdom",
    include: ["helpers/**/*.spec.ts", "helpers/**/*.spec.tsx"],
    exclude: ["helpers/useDebounce.spec.tsx"],
    setupFiles: ["./recovery.vitest.setup.mjs"],
    restoreMocks: false,
    clearMocks: true,
  },
});
EOF

cp "$GITHUB_WORKSPACE/.recovery/spiderweb-exact/recovery.v5.vitest.setup.mjs" recovery.vitest.setup.mjs

find helpers -type f \( -name '*.spec.ts' -o -name '*.spec.tsx' \) -print | sort > recovery-spec-files.txt
count=$(wc -l < recovery-spec-files.txt | tr -d ' ')
echo "SUCCESSOR_SPEC_FILE_COUNT=$count"
test "$count" = "20"
printf 'helpers/useDebounce.spec.tsx\tEMPTY_SPEC_NONEXECUTABLE\n' > recovery-spec-classification.tsv
printf 'helpers/spatialDatasetPipeline.spec.tsx\tFORWARD_RECONSTRUCTION_V1\n' >> recovery-spec-classification.tsv

sha256sum \
  helpers/spatialDatasetPipeline.tsx \
  helpers/spatialDatasetPipeline.spec.tsx \
  helpers/spatialSourceEquivalence.tsx \
  helpers/spatialSourceEquivalence.spec.tsx \
  components/SpatialDatasetIntakePanel.tsx \
  components/SpatialDatasetIntakePanel.module.css \
  components/SpatialAnalysisWorkbench.tsx \
  package.json package-lock.json \
  > forward-v1-hashes.txt

set +e
npx vitest run --config recovery.vitest.config.mts --reporter=verbose 2>&1 | tee recovery-vitest.log
test_status=${PIPESTATUS[0]}
set -e
echo "$test_status" > recovery-test-exit.txt
test "$test_status" = "0"

set +e
npx vite build 2>&1 | tee recovery-build.log
build_status=${PIPESTATUS[0]}
set -e
echo "$build_status" > recovery-build-exit.txt
test "$build_status" = "0"
