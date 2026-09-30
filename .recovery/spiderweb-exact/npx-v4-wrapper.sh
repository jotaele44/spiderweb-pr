#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "vitest" ]]; then
  cp "$GITHUB_WORKSPACE/.recovery/spiderweb-exact/recovery.v4.vitest.config.mts" "$PWD/recovery.vitest.config.mts"
  cp "$GITHUB_WORKSPACE/.recovery/spiderweb-exact/recovery.v4.vitest.setup.mjs" "$PWD/recovery.vitest.setup.mjs"
  sha256sum recovery.vitest.config.mts recovery.vitest.setup.mjs > recovery-harness-v4-hashes.txt
fi
exec "$REAL_NPX" "$@"
