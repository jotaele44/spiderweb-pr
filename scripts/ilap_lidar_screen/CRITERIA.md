# Island-wide lidar change screen: criteria fixed before the first run

Written 2026-11-17, before any island-wide result was computed.

## Inputs
- USGS 3DEP 1 m DEM, PR_PRVI_*_2018 projects (flown 2018) and PR_PuertoRicoUSVI_D24 (flown Dec 2023 to Mar 2025).
- Read at 2 m from the tiles' built-in overviews.

## Change patch (same as Guayanilla)
- Land only: both surfaces valid and above 0.5 m elevation.
- Per-tile vertical offset removed: median difference on ground with slope under 3 degrees.
- Cell flagged when |dz| > 1.0 m. One pass of binary opening. Connected patch area >= 500 m2.
- Each patch records area, volume, max change, mean slope, elevation, centroid.

## Confidence flag
- Mean slope of patch > 25 degrees: "steep, low confidence" (ground classification under canopy differs between surveys). Kept, but ranked separately.

## Candidate definition
- LARGE: |volume| >= 20,000 m3.
- RESIDUAL FILL (the signal sought): a LARGE fill patch that is NOT explained by any of:
  1. a landfill or solid-waste facility within 500 m (EPA FRS/ECHO),
  2. a quarry, mine or sand and gravel site within 500 m (USGS MRDS or visible open pit),
  3. local cut-and-fill balance: cut patches within 1 km totalling at least 50% of the fill volume,
  4. a documented public works, road, housing, port or energy project at the location.
- RESIDUAL CUT is logged too, but a cut alone is not the signal.

## Null definition
- Zero RESIDUAL FILL patches after attribution and visual review = null result for 2018 to 2024 surface spoil at this scale.

## Known limits
- Sees only surface change between the two surveys, on patches >= 500 m2 with > 1 m change.
- Spoil exported by sea or spread thinner than 1 m is invisible.
- Water, and land under 0.5 m, excluded.

## Amendments made 2026-11-17 AFTER the first island-wide results were seen (post hoc, flagged as such)
- A1 Water-surface rule: a patch where >= 60% of cells lie within 0.15 m of the patch median change is classed as a water-level difference (hydro-flattened reservoir or pond), not fill.
- A2 Artifact rule: a patch whose median change exceeds 50 m is classed as a data artifact (one case: 2018 void near 18.26608, -65.75274).
- A3 Reference list for test 1 also included cement and concrete plants (SIC 3241/3273); one attribution rests on that class alone.
- A4 Test 4 (documented project) was NOT applied from documents. Survivors were reviewed by eye on change map, 2024 hillshade and undated USGS imagery; visual classes are judgments, not records.
