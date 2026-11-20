# Access points: scientific method and vertical-datum contract

This document states what the shared terrain and bathymetry processing does,
what it refuses to do, how land elevation and seabed depth may be combined,
and what has and has not been validated.

**Read this first.** Every method here has been verified against synthetic
control surfaces with known answers. None has been scored against independent
field truth, because no such truth set exists in the repository. No precision
or recall is claimed for real terrain or seabed. Thresholds are uncalibrated
defaults. [FACT]

## 1. One processing core, two kinds of measurement

Terrain models from airborne LiDAR and gridded sonar bathymetry are processed
by the same code (`spiderweb/access_points/raster.py`). They are not treated as
the same measurement. A surface records:

- its **kind**: bare-earth terrain, first-return terrain, bathymetry,
  topobathymetry, backscatter intensity, or side-scan intensity;
- its horizontal coordinate reference system and its vertical datum;
- which cells were measured and which were interpolated, when known;
- its vertical uncertainty, when known;
- the source it came from.

**An intensity raster is not a depth surface.** Every height operation refuses
a backscatter or side-scan raster. A side-scan image shows reflectivity, not
depth, and a reflector in a sub-bottom profile is not a passage.

### A surface cannot be built unless

| Requirement | If missing |
|---|---|
| A horizontal coordinate reference system is stated | Refused |
| A height surface names a vertical datum from the controlled vocabulary | Refused |
| The declared sign agrees with the values (optional check) | Refused |

The sign check exists because of a real case in this repository's evidence: a
gridded survey whose values are negative while its label says depth, positive
down. Read literally, that seabed would sit above its datum. With the check
enabled the surface is rejected rather than analysed upside down.

Values are normalised once to **elevation in metres, positive up**. No-data is
kept as no-data.

## 2. Derivatives

| Product | Method | Origin |
|---|---|---|
| Slope | Horn (1981), 3×3 weighted | Existing `gebco/terrain.py`, reused |
| Curvature (profile, plan, general) | Zevenbergen and Thorne (1987) | Existing `gebco/terrain.py`, reused |
| Position index | Cell height minus mean of a disc or ring neighbourhood. The topographic position index on land and the bathymetric position index at sea are the same statistic | New |
| Local relief | Range of valid heights in a window | New |
| Hillshade | Lambertian shading. A rendering, never evidence | New |

All are no-data aware. Neighbourhood operations can run tile by tile with a
halo and give the same result as the untiled run; this is tested.

## 3. Closed-basin delineation

A closed basin is ground that water could not leave. It is found by raising
every basin to its spill level (morphological reconstruction by erosion) and
subtracting the original surface. The difference is fill depth.

**No-data and the grid edge are outlets.** A basin that could drain into ground
nobody measured is not closed, and is not reported. A closed basin is therefore
never built out of unmeasured cells.

**A cell belongs to a basin only where its fill depth can be told apart from
zero.** The floor is the uncertainty of a depth — the square root of two times
the stated vertical uncertainty, because depth is the difference of two
heights — or one micrometre where no uncertainty is stated. Without this floor,
numerical residue on a level rim spreads a basin's outline far beyond the
ground that is measurably lower. (The control suite found exactly this defect
in the first implementation; it is fixed and tested.)

**Where the uncertainty is published cell by cell, the floor is cell by
cell.** A gridded hydrographic survey carries its own uncertainty band, and it
is used as published (`survey.process_seabed`). Three things follow, and each
is stated in the report rather than left to be inferred:

| Depth of a depression against the floor of its own cells | Result |
|---|---|
| Nowhere above the floor | Not reported at all |
| Above the floor, by less than the significance floor (3) | Reported, flagged, CANDIDATE |
| Above the significance floor | Reported, SUPPORTING at most (a grid is never a direct measurement) |

The reported area is the part above the floor, so it is a lower bound. Where
the uncertainty is large, the absence of a detection is not the absence of a
depression: the report counts the covered cells at which a depression of the
minimum depth could not be reported. It also delineates the same surface with
the uncertainty ignored and lists what the rule withheld — a check on the
detector, not evidence.

**A variable-resolution survey file can be read at a finer resolution**
(`survey.read_depth_grid(path, resolution_m)`). Its finer grids are resampled
to the stated cell size: mean elevation of the nodes in each cell, largest of
their uncertainties, empty where no node falls. Nothing is interpolated. The
extract step recomputes every cell from the nodes and stops if any disagrees
(`survey.verify_resampled`). Empty cells are outlets, so a coarse finer grid can
hide a depression but not create one; the report counts them. A depression
smaller than one base cell is flagged as a possible refinement artefact
(informational; no tier is lowered). Every outer depression read this way is
also put to a **seam test** (`survey.seam_test`), written before it was
applied: SEAM_LIKELY only if (1) its median width is at most 2 cells and its
long axis lies within 5° of a grid axis; (2) a level step across that axis —
found by fitting a line to a band of 4 cells on each side and extrapolating
both to the axis — exceeds twice the bands' combined uncertainty, with one
sign, along at least 80% of its length; and (3) the same step continues past
both ends along at least half of an equal length. (1) and (2) without (3) is
STEP_WITHOUT_CONTINUATION, which is indeterminate. A planted seam is found by
it; a trough on smooth ground and a broad bowl are not. The result is
informational and lowers no tier. A reading at another resolution of the
same file is compared with the earlier one by a rule fixed in advance
(`survey.persistence`), and that comparison is a consistency check, never
replication.

Measured for each basin: area, maximum and mean depth, volume, spill and floor
elevation, centroid and deepest point, equivalent diameter, depth-to-diameter
ratio, circularity, elongation, solidity, rectangularity, mean wall slope,
flat-floor fraction, whether it adjoins no-data or the edge, the fraction of
interpolated cells, depth uncertainty, and significance (depth divided by its
uncertainty).

Circularity uses Crofton's perimeter estimator. Against analytic shapes it
returns 0.98 for a disc (exact value 1.0), 0.88 for a square (0.785) and 0.58
for a 4:1 bar (0.503): accurate for curved outlines, biased high by about 0.1
for axis-aligned straight edges. [COMPUTED] For that reason rectangular cuts
are recognised by rectangularity — how much of its bounding box a shape fills —
not by circularity.

### Basins nested inside a larger one

Filling raises a compound depression — several hollows sharing one rim — to a
single spill level, so it comes out as one basin and the hollows inside it are
never reported. The delineation therefore also lowers the water level inside
each basin in fixed steps and reports what separates:

| Rule | Why | Class |
|---|---|---|
| A split needs **two or more** parts that each still meet the depth and area thresholds | A part below threshold is a bump in the floor, not a basin | BINDING |
| The same rule is applied inside each nested basin | Nesting goes as deep as the ground does | BINDING |
| A nested basin's depth is measured from the level at which it is seen to be separate | Its true rim lies less than one step higher, so the depth is a lower bound (0.5 m by default) and is never overstated | BINDING |
| One deep pit in a broad shallow bowl is **not** reported apart from the bowl | It does not separate the water body. A stated limit of this rule; see the second rule below | FACT |
| A cell is under water at a level only where its depth below that level can be told from zero | The same floor an outer basin's outline uses, so numerical residue on a rim is not water | BINDING |
| The outer basins, their measurements and their identifiers are the same with or without it | Existing results do not move | FACT (tested) |

A nested basin carries its level, the identifier of the basin it lies inside,
and an informational `NESTED` flag that lowers no tier. Containment of one
shape in another is not a connection and is never written to the relationship
ledger.

**Default.** Both detectors report nested basins by default since 2026-11-18,
by the owner's decision after the comparison in section 6. The low-level
delineation function still nests only when asked, a declared run must state the
mode it uses, and a run made before the change is pinned to outer basins only,
so its report still reproduces.

**A second rule for the single pit, measured and left off.** `pit_area_jump`
reports a nested basin where the wet area falls by at least a stated factor in
one level step, which is what happens when water drains off a bowl's floor into
a pit. A smooth bowl, cone or funnel never triggers it (tested). On the karst
tile, with a factor of 3, it added 80 objects, recovered none of the three
outlines the splitting rule leaves, and raised only the displaced control, so
by the rule fixed in advance it is not an improvement (run
`2026-11-18-karst-map-pit-rule`). The factor was not tuned against the map. The
rule stays in the code, switched off.

## 4. Survey seams

Where two surveys with a vertical bias meet, the surface steps by nearly the
same amount, with the same sign, all the way along a row or column. Real
relief varies along any straight line. The detector flags a grid line whose
median step is a robust outlier and whose sign is consistent along the line.

Limits: it finds seams aligned with the grid. A seam at an angle, a curved
swath edge, or a bias that varies along the join is not detected. Other
multibeam artefacts (refraction "smiles", motion ripple, outer-beam noise) are
not addressed.

## 5. From shapes to candidates

Detection finds shapes (`spiderweb/access_points/detection.py`). It emits
evidence for **existence** and **morphology** only. It never emits evidence for
a physical opening, accessibility, function or connectivity, and a test asserts
that no detection, whatever its score, lifts a record above the FEATURE rung.

| Input | Rule as coded | Proposed class |
|---|---|---|
| Land basin | Default | CLOSED_DEPRESSION |
| Land basin, rectangularity ≥ 0.88 and at least half the floor under 2° | Shape consistent with excavation | SURFACE_EXCAVATION, with an origin *hypothesis* |
| Land basin, circularity ≥ 0.6, and an evidenced context placing the ground wholly inside a mapped karst-prone unit | Karst reading is plausible | SINKHOLE, with an origin *inference* |
| Seabed basin | Default | SEAFLOOR_DEPRESSION |
| Seabed basin, circularity ≥ 0.7, depth/diameter ≥ 0.15, mean wall slope ≥ 20° | Steep, deep, round | BLUE_HOLE_CANDIDATE — still a candidate |
| Seabed band, slope above a stated threshold, long and narrow | Linear steep band | ESCARPMENT |
| Any basin on a seam, or with at least half its cells interpolated | Possible artefact | UNCLASSIFIED_ANOMALY (land) or SURVEY_ARTIFACT (sea), reported, not dropped |

Inland detection requires a bare-earth model. A first-return surface still
carries buildings and canopy and is refused. Ground classification is the data
producer's; this repository does not perform it.

A basin whose depth is under three times its uncertainty, or whose uncertainty
is unknown, is capped at CANDIDATE for existence.

**The discovery score** (0–100) ranks candidates for review. It combines depth
significance, depth-to-diameter ratio, circularity, wall slope and isolation
from edges, and is reduced for artefact flags. It is a priority, not a
probability, and is listed among the bases that can never support a claim.

## 6. Evaluation

| State | When | What may be said |
|---|---|---|
| SOFTWARE_CONTROL | Scored against synthetic surfaces | The software finds planted shapes |
| EXPLORATORY | No reference labels | Nothing about accuracy |
| REFERENCE_COMPARED | Compared with a published map | Agreement with another interpretation, against a displaced control. Not accuracy |
| MEASURED | Scored against independent field truth | Class-wise precision and recall |

Matching is one-to-one and nearest-first: one detection cannot satisfy two
labels, and one label cannot excuse two detections. Synthetic controls, map
references and field truth cannot be mixed in one score.

**Current state: SOFTWARE_CONTROL, and REFERENCE_COMPARED on one tile.** No
field truth exists, so nothing is MEASURED.

### Comparison with the USGS karst map (2026-11-17)

The reference is the U.S. Geological Survey *Karst Map of Puerto Rico* (2010, a
digital update of Monroe 1976): outlines of 1,173 individual sinkholes the map
calls deeper than 30 m. It was digitised from paper maps with a 50 m contour
interval, and its own metadata says outlines may be offset by as much as 100 m.
It is a published interpretation, not a field survey. 139 of the outlines lie
inside the 10 km elevation tile already held (137 where the 2018 survey has
data).

Two measures are taken, because they answer different questions, each at
several depths and each against a **displaced control** — the same outlines
moved 1 km east, where any agreement is chance. Karst ground is full of
hollows, so a figure means something only by how far it stands above its
control.

| Measure, 2024 survey, 5 m cells | ≥ 10 m | ≥ 20 m | ≥ 30 m | Class |
|---|---|---|---|---|
| Surface: a closed depression inside the outline as drawn | 72% (control 57%) | 57% (28%) | 37% (16%) | COMPUTED |
| Surface: the same, within the map's stated 100 m offset | 99% (97%) | 98% (84%) | 88% (51%) | COMPUTED |
| Detector: reports the mapped sinkhole as its own object | 41% (43%) | 40% (31%) | 32% (16%) | COMPUTED |

What this shows:

| Finding | Class |
|---|---|
| The surface and the map agree where the map is most specific: at 30 m, within the map's own tolerance, 88% of mapped sinkholes are closed depressions that deep, against 51% by chance | COMPUTED |
| Below about 10 m neither measure separates the map from chance on this ground. A shallow basin near a mapped sinkhole is not evidence of anything | COMPUTED |
| The detector under-reports nested sinkholes. Of the 77 mapped sinkholes it does not report as an object, 73 lie inside a larger closed basin: filling raises a whole compound depression to one spill level, and only the outermost basin is reported | COMPUTED |
| The two surveys give the same figures to within one outline, as in the replication test | COMPUTED |
| The gap between "as drawn" and "within 100 m" says the map's positional error matters as much as the method does | INFERENCE |
| Precision is not stated: the map lists only sinkholes deeper than 30 m, so a shallower basin it does not list is not an error | FACT |

**With nested basins reported** (run `2026-11-18-karst-map-nested`: same
labels, tiles, thresholds and window; only the detector option differs). The
reading rule was fixed before any figure was looked at: nesting counts as an
improvement at a depth only where the found fraction rises by more than the
displaced-control fraction does, because more objects always means more chance
matches.

| Detector reports the mapped sinkhole as an object, 2024 survey | ≥ 10 m | ≥ 20 m | ≥ 30 m | Class |
|---|---|---|---|---|
| Outer basins only | 41% (control 43%) | 40% (31%) | 32% (16%) | COMPUTED |
| With nested basins | 92% (74%) | 81% (52%) | 61% (28%) | COMPUTED |
| Gain in found, against gain in control | +51 against +31 points | +42 against +20 | +30 against +13 | COMPUTED |

| Finding | Class |
|---|---|
| By the rule fixed in advance, nesting is an improvement at every depth tested | COMPUTED |
| Of the 73 mapped sinkholes that lay inside a larger basin, 70 are now reported as their own object; 3 remain, the single-pit case above | COMPUTED |
| The margin over chance at 30 m roughly doubles (16 to 33 points). The ratio to chance barely moves (2.0 to 2.2 times): nesting finds more real sinkholes and more chance ones | COMPUTED |
| The object count rises from 1,258 to 3,214 on the tile, with nesting up to 22 levels deep. At shallow depths the control reaches 91%, so a shallow nested basin near a mapped sinkhole still means nothing | COMPUTED |
| The 2018 survey gives the same picture: 32% to 63% at 30 m, control 15% to 28% | COMPUTED |

Nesting is the detectors' default since 2026-11-18, by the owner's decision.
It triples the number of objects, and nothing here says how many of the extra
ones are sinkholes.

No threshold was changed. The result is for one tile of one karst terrain and
does not transfer to other ground or to the seabed. The comparison is recomputed
by `scripts/validate_access_point_detector.py`; the whole-tile figures need the
held tiles, and one 1 km window (eight outlines, too few to conclude from) is
committed so the computation itself can be re-run from the repository.

Two things remain before anything here could be called validated: a rule for
the single pit in a broad bowl that earns its place (the one tried did not),
and ground that someone has visited. [OPEN]

Controls run in `tests/test_access_points_science.py`:

- Negative: flat, tilted, steep-plane and domed surfaces, and noise alone over
  five seeds, yield no basins and no seams.
- Positive: planted Gaussian basins, a steep pit and a rectangular cut are each
  found once, at the planted location, with depth, volume and class as
  expected.
- A basin whose floor is no-data, or that opens to the grid edge, is not
  reported.
- A basin on interpolated cells, or below its uncertainty, is flagged and
  capped.

## 7. Change between surveys

Two surveys of the same ground may be differenced only if they share cells
exactly, share a horizontal reference system, and are on the same vertical
datum or are joined by exactly one certified transform. A change is called
detectable only where it exceeds twice the combined uncertainty. Where either
uncertainty is unknown, detectability is unknown — not assumed.

## 8. Vertical-datum contract

Land elevation and seabed depth are published against different vertical
references and with opposite signs. `spiderweb/access_points/vertical.py` is the
only place that decides whether two vertical values may be combined.

**Controlled vocabulary.** PRVD02, VIVD09, NAVD88 (orthometric); MLLW, MLW, MSL,
MTL, MHW, MHHW, LAT (tidal); NAD83 and WGS84 ellipsoid heights; and
`MSL_ASSUMED` for grids referenced to mean sea level only nominally, which is
kept apart so it can never pass as a tidal measurement. Spellings found in this
repository's registries and receipts resolve to these, including EPSG:5866,
EPSG:5715 and EPSG:5703.

**A placeholder is not a datum.** "Not Provided", "User Specified", "Unknown",
`source_dependent` and similar strings fail closed. This matters in practice:
all four topobathymetric LiDAR inventory rows in the committed Guayama receipt
publish "User Specified" or "Not Provided" as their vertical datum. [FACT:
`evidence/marine/guayama_punta_tuna_v0_1/source_denominator_receipt.json`]

**No built-in offsets.** The separation between a tidal datum and an
orthometric datum is specific to a place and an epoch. The package ships no
numeric offset. Two values on different datums are combined only through a
transform that names its authority, optionally its uncertainty and the area
where it is valid. Two applicable transforms are an ambiguity and are refused.

**Uncertainty** combines by root-sum-square. If any part is unknown, the total
is unknown.

**Joining a land surface and a seabed surface:**

| State | Meaning | What may be drawn |
|---|---|---|
| SAME_REFERENCE | Both state the same datum | One shared vertical axis |
| TRANSFORMED | A certified transform applies here | One shared axis, with the authority named |
| SEPARATE_SURFACES_ONLY | Different datums, no transform; or one is on an assumed datum | Each surface on its own axis; no difference computed |
| BLOCKED_UNKNOWN_DATUM | A datum is missing or a placeholder | Nothing is combined |

**Cross-sections** (`spiderweb/access_points/transects.py`) read the cell under
each station — no resampling, no smoothing — and report every stretch with no
survey coverage as a gap with its length. Nothing is interpolated across a gap,
and a continuous land-to-sea profile is never produced across ground nobody
measured.

**Coastlines** (`spiderweb/access_points/coastal.py`). A coastline depends on
the tidal datum that defines it and on its survey date. Each is kept as a
dated, sourced version, and a geometry is classified against each version
separately using the existing six-state predicate (fully within, partial, touch
only, outside, empty, unresolved). A point that is sea on a mean-high-water
shoreline and land on a lower-water one is reported as exactly that; it is not
assigned to a registry by geometry.

### A stated datum that cannot be true where the data lie

Real products showed a case the contract did not cover: a datum that is stated,
is not a placeholder, and is still not usable as stated. Both elevation tiles
processed on 2026-11-17 say NAVD88, in a programme-wide sentence written for the
North American mainland; their own metadata files have no structured vertical
element, and NAVD88 is not realised in Puerto Rico (the datum there is PRVD02).
The elevation inventory says NAVD88 for the same projects.

The rule now is:

| Step | Behaviour | Class |
|---|---|---|
| Record | The datum is kept exactly as stated, with where the statement was found | BINDING |
| Check | `regional_plausibility` says whether that datum is realised at the location | COMPUTED |
| Single-surface analysis | Allowed: closed-basin shape does not depend on the datum | FACT |
| Join to a surface on another reference | Refused while the statement is implausible for the region | BINDING |
| Two surfaces with the same implausible statement | Compared cell by cell; agreement is reported as measured, never assumed | COMPUTED |

The check is a coarse box test on a stated orthometric datum. It is a sanity
check, not a geodetic definition, and it never replaces the stated datum with
another one.

### A tidal datum, and a depth name on elevation values

The first seabed product read (2026-11-18) states MLLW, in a structured
metadata element and in the name of its coordinate system. Two things were
recorded rather than resolved:

| Finding | Behaviour | Class |
|---|---|---|
| MLLW is a tidal datum. It has no regional extent to test a statement against | `regional_plausibility` returns NOT_ASSESSED. It is never reported as plausible, so the surface is not joinable to a land surface | COMPUTED |
| The coordinate system is named "MLLW depth" with a downward axis, while the stored values are elevations, all negative | The values are used as stored, bound positive-up, and not re-signed; the product's own name is kept beside them. A grid declared submerged whose values lie above its datum is refused (`SignConventionError`) | BINDING |
| Depths relative to MLLW are not heights on PRVD02 or any orthometric datum | Nothing is converted. No certified transform is held | FACT |

Closed-depression shape does not depend on the datum, so neither finding stops
single-surface analysis.

### Failure behaviour

| Input | Result |
|---|---|
| Grid without a coordinate reference system | `MissingCRSError` |
| Missing, placeholder or unrecognised datum | `UnknownVerticalDatumError` |
| Reference naming two different datums | `UnknownVerticalDatumError` |
| Depth code declared positive-up, or height code positive-down | `VerticalCompatibilityError` |
| Values contradict the declared sign | `SignConventionError` |
| Different datums, no transform | `VerticalCompatibilityError`, or the join state above |
| Height operation on an intensity raster | `NotAnElevationSurfaceError` |
| Grids that do not share cells | `GridMismatchError` |

## 9. Hardening of existing gates

The audit found three loopholes in pre-existing code, each confirmed by running
it. All three are closed in this change, with tests:

| Loophole | Before | Now |
|---|---|---|
| `VerticalReference.is_fully_bound` in `gebco/marine_evidence.py` | Any non-empty string counted, so two surveys both labelled "Not Provided" compared as if on one datum | A placeholder does not bind a reference |
| `classify_feature_evidence`, same file | A direct observation with no acquisition root ranked above one whose root was known | A rootless observation is single-sensor support at most |
| `source_adapters/ncei_coastal_dem/datum_policy.py` | A selection whose datum was `source_dependent` passed as "same datum" | It requires review |

## 10. What is absent

Stated so that nobody assumes it exists: point-cloud reading (LAS, LAZ, COPC),
ground classification, bare-earth extraction, contour extraction and contour
trees, flow routing, local relief models beyond a windowed range, interpretation
of side-scan, backscatter or sub-bottom data, multibeam artefact filtering
beyond grid-aligned seams and the seam test above, a way to say what a small
depression that is neither seam-like nor a resolved pit actually is, a second
seabed survey or epoch to replicate the first (a declared search found only raw
pings from the independent cruises that cross the depressions), processing of
raw multibeam soundings, a certified transform
between a tidal datum and an orthometric one, reprojection of geographic grids
inside this package, per-cell uncertainty for elevation tiles, a rule that separates a single pit from the
broad bowl it sits in and is shown to help, and any field-visited truth set. A projected GeoTIFF
elevation tile can be read (`survey.py`); one has been. The base grid of a
gridded bathymetric survey file (BAG) can be read, with its uncertainty band,
and so can its finer grids at a stated resolution; one file has been read both
ways.
