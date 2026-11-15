#!/bin/sh
# Launcher (Linux). Double-click where your file manager allows executing
# scripts, or run ./PRII-SPIDERWEB.sh. First run installs dependencies (needs
# internet once); later runs start the app directly and work offline.
set -eu
cd "$(dirname "$0")"

# Newest Python that meets the project's 3.11 floor.
PYTHON=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 \
    && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' 2>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Python 3.11 or newer is required (e.g. sudo apt install python3 python3-venv)."
  exit 1
fi

if ! "$PYTHON" desktop/setup.py --ensure; then
  echo
  echo "Setup did not finish; the last lines above say which step stopped."
  if [ -t 0 ]; then
    printf '%s' "Press Enter to close… "
    read -r _
  fi
  exit 1
fi
exec .venv/bin/python desktop/launch.py "$@"
