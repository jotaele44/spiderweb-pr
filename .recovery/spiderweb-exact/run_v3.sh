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
    if not line.strip():
        continue
    sha, size, path = line.split("  ", 2)
    expected[path] = (int(size), sha)
actual = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
if set(actual) != set(expected):
    raise SystemExit("member-set mismatch")
for rel in actual:
    data=(root/rel).read_bytes()
    size,sha=expected[rel]
    if len(data)!=size or hashlib.sha256(data).hexdigest()!=sha:
        raise SystemExit(f"member mismatch: {rel}")
if len(actual)!=272:
    raise SystemExit(f"expected 272 files, got {len(actual)}")
print("EXACT_MEMBER_VERIFICATION=PASS")
print("RECOVERED_FILE_COUNT=272")
PY

cd "$ROOT"
cp package.json package.original.json
sha256sum package.original.json > recovery-package-hashes.txt
export NPM_CONFIG_LEGACY_PEER_DEPS=true
npm install --no-audit --no-fund --ignore-scripts
npm install --save-dev --no-audit --no-fund --ignore-scripts   vitest@3.2.4 jsdom@26.1.0 @testing-library/react@16.2.0 @testing-library/dom@10.4.1
sha256sum package.json package-lock.json >> recovery-package-hashes.txt
node -v > recovery-environment.txt
npm -v >> recovery-environment.txt
printf 'NPM_CONFIG_LEGACY_PEER_DEPS=true\n' >> recovery-environment.txt

cat > recovery.vitest.config.mts <<'EOF'
import { defineConfig } from "vitest/config";
export default defineConfig({
  test: {
    globals: true,
    environment: "jsdom",
    include: ["helpers/**/*.spec.ts", "helpers/**/*.spec.tsx"],
    exclude: ["helpers/useDebounce.spec.tsx"],
    setupFiles: ["./recovery.vitest.setup.mjs"],
    restoreMocks: true,
    clearMocks: true,
  },
});
EOF

cat > recovery.vitest.setup.mjs <<'EOF'
import { vi, expect } from "vitest";

expect.extend({
  toBeTrue(received) {
    return {
      pass: received === true,
      message: () => `expected ${received} to be true`,
    };
  },
  toBeFalse(received) {
    return {
      pass: received === false,
      message: () => `expected ${received} to be false`,
    };
  },
});

function jasmineCompatSpy(spy) {
  const api = spy;
  api.and = {
    returnValue(value) { spy.mockReturnValue(value); return api; },
    resolveTo(value) { spy.mockResolvedValue(value); return api; },
    callFake(fn) { spy.mockImplementation(fn); return api; },
  };
  api.calls = {
    mostRecent() { return { args: spy.mock.calls.at(-1) ?? [] }; },
    count() { return spy.mock.calls.length; },
  };
  return api;
}
globalThis.spyOn = (target, key) => jasmineCompatSpy(vi.spyOn(target, key));
globalThis.jasmine = {
  createSpy(name) { return jasmineCompatSpy(vi.fn().mockName(name)); },
};
EOF
sha256sum recovery.vitest.config.mts recovery.vitest.setup.mjs >> recovery-package-hashes.txt

find helpers -type f \( -name '*.spec.ts' -o -name '*.spec.tsx' \) -print | sort > recovery-spec-files.txt
count=$(wc -l < recovery-spec-files.txt | tr -d ' ')
echo "RECOVERED_SPEC_FILE_COUNT=$count"
test "$count" = "18"
printf 'helpers/useDebounce.spec.tsx\tEMPTY_SPEC_NONEXECUTABLE\n' > recovery-spec-classification.tsv

set +e
npx vitest run --config recovery.vitest.config.mts --reporter=verbose 2>&1 | tee recovery-vitest.log
status=${PIPESTATUS[0]}
set -e
echo "$status" > recovery-test-exit.txt
exit 0
