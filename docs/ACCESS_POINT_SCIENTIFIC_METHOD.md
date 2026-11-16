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
| MEASURED | Scored against independent field truth | Class-wise precision and recall |

Matching is one-to-one and nearest-first: one detection cannot satisfy two
labels, and one label cannot excuse two detections. Synthetic and field truth
cannot be mixed in one score.

**Current state: SOFTWARE_CONTROL only.** A labelled set could be assembled
from published sinkhole and cave layers, with quarries, graded urban ground and
reservoirs as negative controls, and a small frozen raster. That is the next
scientific step and has not been done. [OPEN]

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
beyond grid-aligned seams, reading of gridded survey files into this pipeline,
and any labelled truth set.
