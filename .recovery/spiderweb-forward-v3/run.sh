#!/usr/bin/env bash
set -euo pipefail
ROOT="$RUNNER_TEMP/recovered-forward-v3"
ARCHIVE="$RUNNER_TEMP/spiderweb_exact.tar.gz"
rm -rf "$ROOT"; mkdir -p "$ROOT"
cat .recovery/spiderweb-exact/part-000 .recovery/spiderweb-exact/part-001 .recovery/spiderweb-exact/part-002 .recovery/spiderweb-exact/part-003 > "$ARCHIVE"
echo "b5e8c8ce51d221819d4f0040bcde5eeb984769cab2fd3165cad7082802723815  $ARCHIVE" | sha256sum -c -
tar -xzf "$ARCHIVE" -C "$ROOT"
python - <<'PY'
from pathlib import Path
import hashlib,os
root=Path(os.environ["RUNNER_TEMP"])/"recovered-forward-v3"; expected={}
for line in Path(".recovery/spiderweb-exact/member_manifest.txt").read_text().splitlines():
    if line.strip():
        sha,size,path=line.split("  ",2); expected[path]=(int(size),sha)
actual=sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
if set(actual)!=set(expected): raise SystemExit("baseline member-set mismatch")
for rel in actual:
    b=(root/rel).read_bytes(); size,sha=expected[rel]
    if len(b)!=size or hashlib.sha256(b).hexdigest()!=sha: raise SystemExit(f"baseline member mismatch: {rel}")
if len(actual)!=272: raise SystemExit(f"expected 272 baseline files, got {len(actual)}")
print("BASELINE_EXACT_MEMBER_VERIFICATION=PASS"); print("BASELINE_FILE_COUNT=272")
PY

mkdir -p "$ROOT/components" "$ROOT/helpers"
cp .recovery/spiderweb-forward-v1/overlay/helpers/spatialDatasetWorkflow.tsx "$ROOT/helpers/"
cp .recovery/spiderweb-forward-v1/overlay/helpers/spatialDatasetWorkflow.spec.tsx "$ROOT/helpers/"
cp .recovery/spiderweb-forward-v1/overlay/components/SpatialDatasetIntake.tsx "$ROOT/components/"
cp .recovery/spiderweb-forward-v1/overlay/components/SpatialDatasetIntake.spec.tsx "$ROOT/components/"
cp .recovery/spiderweb-forward-v1/overlay/components/SpatialAnalysisWorkbench.tsx "$ROOT/components/"
cp .recovery/spiderweb-forward-v2/overlay/helpers/spatialAuthorityReceipts.tsx "$ROOT/helpers/"
cp .recovery/spiderweb-forward-v2/overlay/helpers/spatialAuthorityReceipts.spec.tsx "$ROOT/helpers/"
sha256sum .recovery/spiderweb-forward-v1/overlay/helpers/* .recovery/spiderweb-forward-v1/overlay/components/* .recovery/spiderweb-forward-v2/overlay/helpers/* .recovery/spiderweb-forward-v2/evidence.json .recovery/spiderweb-forward-v3/render-qa.mjs > "$ROOT/forward-v3-overlay-hashes.txt"

cd "$ROOT"
cp package.json package.original.json
export NPM_CONFIG_LEGACY_PEER_DEPS=true
npm install --no-audit --no-fund --ignore-scripts
npm install --save-dev --no-audit --no-fund --ignore-scripts vitest@3.2.4 jsdom@26.1.0 @testing-library/react@16.2.0 @testing-library/dom@10.4.1
cp "$GITHUB_WORKSPACE/.recovery/spiderweb-exact/recovery.v5.vitest.config.mts" recovery.vitest.config.mts
cp "$GITHUB_WORKSPACE/.recovery/spiderweb-exact/recovery.v5.vitest.setup.mjs" recovery.vitest.setup.mjs
python - <<'PY'
from pathlib import Path
p=Path("recovery.vitest.config.mts")
p.write_text(p.read_text().replace('include: ["helpers/**/*.spec.ts", "helpers/**/*.spec.tsx"],','include: ["helpers/**/*.spec.ts", "helpers/**/*.spec.tsx", "components/**/*.spec.ts", "components/**/*.spec.tsx"],'))
PY
sha256sum package.original.json package.json package-lock.json recovery.vitest.config.mts recovery.vitest.setup.mjs > forward-v3-runtime-hashes.txt
node -v > forward-v3-environment.txt; npm -v >> forward-v3-environment.txt
find helpers components -type f \( -name '*.spec.ts' -o -name '*.spec.tsx' \) -print | sort > forward-v3-spec-files.txt
count=$(wc -l < forward-v3-spec-files.txt | tr -d ' '); echo "FORWARD_V3_SPEC_FILE_COUNT=$count"; test "$count" = "21"
printf 'helpers/useDebounce.spec.tsx\tEMPTY_SPEC_NONEXECUTABLE\n' > forward-v3-spec-classification.tsv

set +e
npx vitest run --config recovery.vitest.config.mts --reporter=verbose 2>&1 | tee forward-v3-vitest.log
test_status=${PIPESTATUS[0]}
set -e
echo "$test_status" > forward-v3-test-exit.txt
if [ "$test_status" -ne 0 ]; then exit 0; fi

npm install --save-dev --no-audit --no-fund --ignore-scripts playwright@1.55.0
npx playwright install --with-deps chromium
npx vite build 2>&1 | tee forward-v3-build.log
mkdir -p rendered
npx vite preview --host 127.0.0.1 --port 4173 > forward-v3-preview.log 2>&1 &
preview_pid=$!
trap 'kill "$preview_pid" 2>/dev/null || true' EXIT
ready=0
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:4173/spatial-analysis >/dev/null; then ready=1; break; fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then echo "preview did not become ready"; exit 1; fi
node "$GITHUB_WORKSPACE/.recovery/spiderweb-forward-v3/render-qa.mjs" 2>&1 | tee forward-v3-render.log
sha256sum rendered/*.png rendered/rendered-qa.json > forward-v3-render-hashes.txt
echo 0 > forward-v3-render-exit.txt
