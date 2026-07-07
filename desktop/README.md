# Run Spiderweb as a desktop app

Double-click the launcher for your system in the repo root:

| System | File |
|---|---|
| macOS | `PRII-SPIDERWEB.command` |
| Windows | `PRII-SPIDERWEB.bat` |
| Linux | `PRII-SPIDERWEB.sh` |

The **first run** needs an internet connection once: it creates a private
`.venv` and installs the small server dependencies (requires
[Python 3.10+](https://www.python.org/downloads/); **no Node.js needed** —
the UI is the standalone `dashboard/dashboard.html` viewer with vendored
React/Tailwind under `dashboard/vendor/`). Every later run starts instantly
and **works fully offline**.

## What it shows

The dashboard reads a JSON snapshot of your local flight database
(`~/flight_database.db`, exported to `outputs/dashboard_data.json` during
setup via `run_all.py --export-json`). Without a database the app opens with
empty metrics and a source-status panel — run the spiderweb pipeline
(`python run_all.py …`) to populate it, then re-run
`python desktop/setup.py --force` (or export manually) to refresh the
snapshot. Optional layers (`fr24_dashboard_review_queue.json`,
`contract_finance_layer_report.json`) appear automatically when the
corresponding exports exist in `outputs/`.

The heavy analysis extras (`rag` LLM stack, geospatial ingest) are **not**
part of the desktop install; they remain the documented developer CLI paths.

## How it works

- `desktop/config.py` — per-repo settings (title, dashboard/outputs paths).
- `desktop/app_server.py` — FastAPI serving `dashboard/` and `outputs/`
  from one local port (replaces the `python -m http.server` step from the
  dashboard header docs).
- `desktop/launch.py` — picks a free port, starts uvicorn, opens a native
  [pywebview](https://pywebview.flowrl.com/) window (falls back to the
  default browser). Flags: `--no-window`, `--browser`, `--smoke`.
- `desktop/setup.py` — idempotent one-time setup (`--force` to redo).

## Command line

```bash
python desktop/setup.py          # one-time setup + data snapshot
.venv/bin/python desktop/launch.py            # native window
.venv/bin/python desktop/launch.py --browser  # browser tab instead
.venv/bin/python desktop/launch.py --no-window  # server only
```
