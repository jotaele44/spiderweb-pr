# Run Spiderweb as a desktop app

Double-click the launcher for your system in the repo root:

| System | File |
|---|---|
| macOS | `PRII-SPIDERWEB.command` or `PRII-SPIDERWEB.app` |
| Windows | `PRII-SPIDERWEB.bat` |
| Linux | `PRII-SPIDERWEB.sh` |

The **first run** needs an internet connection once: it creates a private
`.venv`, installs the desktop-scoped Python dependencies, and builds the
Vite single-page app under `server/frontend`. It requires
[Python 3.11+](https://www.python.org/downloads/) to be installed. Node.js
is needed for the build but does not have to be installed: setup uses a copy
it finds (on `PATH`, or under nvm, fnm, asdf, Volta, Homebrew) and otherwise
downloads the current Node 22 release from nodejs.org into a private `.node/`
folder in the checkout, after verifying its checksum. `git` is optional too —
without it the pinned `prii-desktop` runtime is installed from the same
commit's source archive. Every later run starts instantly and **works
offline** — the app serves its FastAPI backend and the built dashboard from a
local server and shows it in a native window.

Offline caveat: map basemap tiles are fetched from the internet
(OpenStreetMap), so without a connection the map background is blank while
all other data, tables, and charts keep working. The same holds for the
"Aerial imagery" layer on the Spatial map: its tiles are rendered on demand
from NOAA's public `noaa-eri-pds` bucket, so with no connection the flight
list still loads but the imagery and its footprints report an error.

First launch also creates a writable workspace and prepares `server/priis.db`
for the live backend. It seeds the diagnostic dataset only when the database
is absent; existing user state is left untouched.

## How it works

- `desktop/config.py` — the only per-repo file (window title, branding,
  paths, and the dotted import path of the FastAPI app object). Also flags
  `ATTACH_FRONTEND = True` so the shared runtime serves the built SPA on top
  of the API.
- `desktop/app_server.py` — the thin Spiderweb adapter that mounts the real
  FastAPI backend (and `/outputs`) for the shared runtime to attach the SPA
  to.
- `desktop/launch.py` — a thin adapter that hands `desktop/config.py` to the
  shared `prii_desktop` runtime, which picks a free port, starts uvicorn,
  and opens a native [pywebview](https://pywebview.flowrl.com/) window
  (falls back to the default browser).
- `desktop/setup.py` — idempotent one-time setup (`--force` to redo); finds or
  downloads Node.js for the dashboard build. It
  installs only the FastAPI-scoped dependencies declared in
  `requirements-desktop.txt` (`fastapi`, `uvicorn`, `pywebview`,
  `sse-starlette`, `aiosqlite`, plus the shared `prii-desktop` runtime) — not
  the full data-pipeline extras (`airspace`/`rag`/`earthgpt`) from the root
  `requirements.txt`, which the desktop app doesn't need to launch.

Native setup, repair, diagnostics, the per-user lock, and the pywebview
lifecycle itself live in the shared `thehub-pr/packages/prii_desktop`
runtime that `desktop/launch.py` and `desktop/setup.py` depend on.

## Command line

```bash
python3 desktop/setup.py          # one-time setup
.venv/bin/python desktop/launch.py            # native window
.venv/bin/python desktop/launch.py --browser  # browser tab instead
.venv/bin/python desktop/launch.py --no-window  # server only
```

## macOS app icon

`PRII-SPIDERWEB.app` is a double-click macOS app (Apple-silicon and Intel).
Double-click it in Finder and the dashboard opens in its own window. The
first launch runs the same one-time setup described above: the app opens a
Terminal window that shows the setup's progress and then reopens the app by
itself — there is nothing to type. After that it starts straight away, with
no Terminal, and works offline.

Because the app is a small self-locating wrapper around `desktop/launch.py`,
it must stay at the repo root (it finds the repo from its own location).
Release CI (`desktop-build.yml`) separately builds and smokes a frozen,
no-Python-required standalone app on macOS, Windows, and Linux and packages
the macOS build as a `.dmg` attached to `desktop-v*` releases — that's an
alternative distribution channel, not a requirement for running the app from
this checkout.

## If macOS blocks the first open

The app is safe — it's an open-source launcher script you can read in
`Contents/MacOS/`. macOS blocks it only because it isn't signed with a paid
Apple Developer ID or notarized by Apple, so the first open may show *"cannot
be opened because Apple cannot check it for malicious software"* or an
*"unidentified developer"* notice. That's macOS quarantining files downloaded
from the internet (it happens especially with GitHub's **Download ZIP**). Any
one of the following clears it — you only do this once per download:

- **Easiest — run the helper.** Double-click **`Fix-Gatekeeper.command`** in
  the repo root, then open the app normally. If the helper is itself
  blocked, right-click it → **Open** to run it once.
- **Terminal (always works).** Paste this into Terminal (pasting a command is
  never blocked), then press Return:
  ```bash
  xattr -dr com.apple.quarantine "/path/to/spiderweb-pr/PRII-SPIDERWEB.app"
  ```
  Tip: type `xattr -dr com.apple.quarantine ` (with a trailing space) and
  drag the app onto the Terminal window to fill in its path.
- **System Settings.** Double-click the app, let macOS block it, then open
  **System Settings → Privacy & Security**, scroll to the message naming the
  app, and click **Open Anyway**. On macOS Sequoia 15 and later this replaces
  the old right-click → **Open** trick.

## If first-run setup does not finish

The setup window (`PRII-SPIDERWEB.app/Contents/Resources/first-run-setup.command`)
never asks for a command. If a step fails — usually no internet connection —
it names the step and waits; press Return in that window to try again. Its
output is also saved to `~/Library/Logs/PRII-Spiderweb/setup.log`.

The one thing it cannot install is Python itself: when no Python 3.11+ is
found it opens the python.org download page and waits for the installer to
be run.

## If the app says it is running from a temporary copy

Opening `PRII-SPIDERWEB.app` straight out of an unzipped download makes
macOS run it from a throwaway read-only copy under
`/private/var/folders/…/AppTranslocation/…`, where the rest of the checkout
is not present and no `.venv` can be written. Move the folder somewhere else
(your home folder is fine), double-click `Fix-Gatekeeper.command` once, then
open the app again. Running `PRII-SPIDERWEB.command` instead also avoids it —
only `.app` bundles are translocated.
