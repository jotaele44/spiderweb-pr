# Monorepo split evaluation (T12-97)

A decision record on whether to split this repository into multiple packages.

## Context
The repo bundles several loosely-coupled subsystems behind one package with
optional-dependency extras (Theme 1): `airspace`, `gebco`, `earthgpt`, `rag`,
`server`, `federation`. Each already installs independently and is import-smoke
tested in the `install-matrix` CI job.

## Options

### A. Stay a monorepo with extras (recommended, status quo)
- **Pros:** one CI pipeline, one version, shared contracts (`federation/`,
  `provenance_utils.py`) stay in lockstep; extras already give clean install
  boundaries; cross-subsystem refactors are atomic.
- **Cons:** a full clone pulls every subsystem's docs/tests; the heavy `rag`
  stack is excluded from CI rather than physically separated.

### B. Split into multiple repos (e.g. `spiderweb-core`, `spiderweb-gebco`, `spiderweb-rag`)
- **Pros:** smaller clones; independent release cadence; heavy deps isolated.
- **Cons:** cross-repo version negotiation (the federation contract already has
  to do this once, see T9-77); shared utilities must be published as packages;
  multiplies CI/release plumbing; higher coordination cost for the current
  single-maintainer cadence.

## Decision
**Stay a monorepo with extras (Option A)** for now. The extras model already
delivers most of the isolation benefit (per-subsystem install + import smoke)
without the cross-repo coordination tax. Re-evaluate if/when:

1. a subsystem gains an independent release consumer, or
2. the `rag` stack needs to ship/version on its own, or
3. clone size or CI wall-time becomes a real bottleneck.

The extras boundaries in `pyproject.toml` are the seam along which a future
split would cut, so keeping them clean (Themes 1 & 6) keeps that option open.
