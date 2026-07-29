# Run Spiderweb as a desktop GIS app

Double-click the launcher for your system in the repository root:

| System | File |
|---|---|
| macOS | `PRII-SPIDERWEB.command` |
| Windows | `PRII-SPIDERWEB.bat` |
| Linux | `PRII-SPIDERWEB.sh` |

The first source-checkout run creates a private `.venv`, installs the desktop
server dependencies, and builds `server/frontend`. It therefore requires
Python 3.11+, Node.js 22+, and a one-time internet connection. Packaged
PyInstaller releases already contain the built frontend and do not require
Python or Node.js.

## What it shows

The desktop root is the same canonical spatial-intelligence workbench served by
the backend: catalog-driven map layers, site/event/anomaly inspection,
provenance, temporal filters, and GeoJSON/CSV exports.

Data availability is explicit. If `server/priis.db` or a catalogued geometry
artifact is absent, the application reports the unavailable endpoint or layer;
it does not manufacture a demo dataset.

## How it works

- `desktop/config.py` points to `server/frontend/dist/index.html`.
- `desktop/app_server.py` combines the canonical FastAPI backend and built SPA
  on one local origin.
- `desktop/launch.py` starts uvicorn and opens a native pywebview window, with a
  browser fallback. `--smoke` verifies both backend health and canonical HTML.
- `desktop/setup.py` installs dependencies and builds the frontend when needed.
- `desktop/pyinstaller.spec` bundles the frontend, catalog, backend, and optional
  local spatial data.

## Source-checkout commands

```bash
python desktop/setup.py
.venv/bin/python desktop/launch.py
.venv/bin/python desktop/launch.py --browser
.venv/bin/python desktop/launch.py --no-window
```

Use `.venv\Scripts\python.exe` instead on Windows.

## Packaged builds

The `desktop-build` workflow verifies and builds the canonical frontend, freezes
the app on Linux, macOS, and Windows, and runs `desktop/launch.py --smoke`
against each frozen bundle. Release tags matching `desktop-v*` also receive the
zipped bundles and macOS disk image.
