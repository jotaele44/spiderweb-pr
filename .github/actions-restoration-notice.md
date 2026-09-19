# GitHub Actions Restoration Notice

**Date:** 2026-09-19  
**Status:** RESTORED

## Summary

GitHub Actions runners were unavailable from approximately 2026-09-06 through
2026-09-19. Workflows triggered during that window completed as `failure`
immediately with `runner_id: 0`, `steps: []`, and no usable logs.

## Affected window

Commits merged while Actions was unavailable used local verification in place
of CI. These commits now need to be re-verified against live runners.

Key affected merge: SHA `85089a888391eb494ad6b047831684cd6b301162`
("GIS hardening: lossy-lineage admission and rendered parity") — merged
under the owner's standing billing/runner exception.

## Required re-runs

The following workflow classes should be re-run on the current `main` head:

- CI (core test suite)
- HAF Contract Gate
- Federation Compatibility
- Federation Spatial Index
- CodeQL
- Admin Control Plane Boundary
- Secret scan
- PRII Smoke Gate
- Aguadilla subsurface benchmark (issue #350)

## Exit criteria

Close this notice once at least one representative workflow on the current
`main` head allocates a real runner (`runner_id != 0`), executes its steps,
and publishes usable logs.

## Related issues

- #350 BLOCKER: GitHub Actions jobs fail before runner assignment
