# earthgpt

Satellite-imagery context + metrics layer, with a self-test gate wired into the
release pipeline.

## What's here
- `metrics.py` — per-image metrics (`compute_single_metrics`).
- `selftest.py` — the 7-gate self-test (`run_selftest`) the release gate and CI
  run as a non-gating WARNING-on-failure check.
- `context*.py`, `corridor_graph.py`, `features_lite.py` — context normalization,
  corridor graphing, lightweight feature extraction.
- `async_fetch.py`, `cache_index.py`, `io_utils.py`, `ios_profile.py` — fetch,
  caching, and IO helpers.

## Install
```bash
pip install -e ".[earthgpt]"
```

## Self-test
```bash
python -c "from earthgpt.selftest import run_selftest; print(run_selftest())"
```

CI runs this in the `test` job and the release gate runs it as
`earthgpt_selftest` (degrades to WARNING, never FAIL — see `release_check.py`).
