#!/bin/bash
# One-time setup for PRII-SPIDERWEB.app, opened in Terminal by the app itself
# when the checkout is not set up yet. Runs desktop/setup.py where its progress
# is visible, then reopens the app. Nothing here asks the person to type a
# command: a failed step is explained and retried on Return.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$(cd "$HERE/../.." && pwd)"
REPO="$(cd "$APP/.." && pwd)"
cd "$REPO" || exit 1

# python.org installs to /usr/local/bin and the framework dir; Homebrew to
# /opt/homebrew/bin on Apple silicon.
export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:$PATH"

LOG_DIR="$HOME/Library/Logs/PRII-Spiderweb"
mkdir -p "$LOG_DIR" 2>/dev/null || LOG_DIR="${TMPDIR:-/tmp}"
LOG="$LOG_DIR/setup.log"

# Newest Python that meets the project's 3.11 floor. A bare `python3` is often
# Apple's 3.9, which is too old.
find_python() {
  local candidate
  for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 \
      && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' 2>/dev/null; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

echo "Spiderweb — PRII: one-time setup"
echo "This needs an internet connection and takes a few minutes."
echo

opened_python_page=0
while true; do
  if ! PY="$(find_python)"; then
    echo "Python 3.11 or newer is not installed on this Mac."
    if [ "$opened_python_page" = 0 ]; then
      echo "Opening the Python download page — run the installer it offers."
      open "https://www.python.org/downloads/" 2>/dev/null || true
      opened_python_page=1
    fi
    echo
    read -r -p "When Python is installed, press Return to continue… " _
    hash -r
    continue
  fi

  echo "Using $("$PY" --version 2>&1) at $PY"
  if "$PY" desktop/setup.py 2>&1 | tee "$LOG"; then
    echo
    echo "Setup finished. Opening Spiderweb…"
    open "$APP"
    exit 0
  fi

  echo
  echo "Setup did not finish; the last lines above say which step stopped."
  echo "A copy of this output is saved at: $LOG"
  echo
  read -r -p "Press Return to try again (or close this window to stop)… " _
  echo
done
