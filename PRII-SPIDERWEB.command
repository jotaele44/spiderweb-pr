#!/bin/bash
# Double-click launcher (macOS). First run installs dependencies (needs
# internet once); later runs start the app directly and work offline.
set -euo pipefail
cd "$(dirname "$0")"

# python.org installs to /usr/local/bin and the framework dir; Homebrew to
# /opt/homebrew/bin on Apple silicon.
export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:$PATH"

# Newest Python that meets the project's 3.11 floor. A bare `python3` is often
# Apple's 3.9, which is too old.
PYTHON=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 \
    && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' 2>/dev/null; then
    PYTHON="$(command -v "$candidate")"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Python 3.11 or newer is required. Install it from https://www.python.org/downloads/"
  [ -t 0 ] && read -r -p "Press Enter to close…"
  exit 1
fi

if ! "$PYTHON" desktop/setup.py --ensure; then
  echo
  echo "Setup did not finish; the last lines above say which step stopped."
  [ -t 0 ] && read -r -p "Press Enter to close…"
  exit 1
fi
exec .venv/bin/python desktop/launch.py "$@"
