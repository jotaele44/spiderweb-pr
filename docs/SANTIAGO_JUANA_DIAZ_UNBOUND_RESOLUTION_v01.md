# Santiago Triangle — Juana Díaz Unbound Screenshot Resolution v0.1

## Scope

This adjudication tests whether `IMG_4020.jpeg` and `IMG_4021.jpeg` can be hard-bound to any Santiago relevance zone. The permitted binders are limited to: (1) explicit coordinates, (2) a uniquely identifying named landmark, or (3) independently georegistrable viewport context. No inferred SZ assignment is permitted.

## Result

Both screenshots remain `UNRESOLVED`.

| Screenshot | GPS EXIF | Unique named landmark | Independent viewport georegistration | Final state |
|---|---|---|---|---|
| `IMG_4020.jpeg` | absent | absent | insufficient | `UNRESOLVED` |
| `IMG_4021.jpeg` | absent | absent | insufficient | `UNRESOLVED` |

Neither image may contribute to relevance score, identity, connectivity, or zone promotion.

## Why road/vegetation morphology is insufficient

`IMG_4020.jpeg` shows grading/disturbance, a local road and vegetated terrain. `IMG_4021.jpeg` shows rural/residential/agricultural terrain. These patterns are non-unique in the Juana Díaz landscape. A white selected-feature boundary visible in a screenshot is not itself a geodetic locator because multiple Santiago cells share the same grid geometry and screen orientation/zoom are not frozen as map coordinates.

## Public coordinate anchors found during adjudication

Public sources provide two useful but non-equivalent anchors:

1. A published Cueva Naranjo conservation record gives approximately `18.066528, -66.469714`, which falls in `SZ-0015`.
2. An EPA ECHO facility record for `PRODUCTOS DE AGREGADOS - CANTERA NARANJO`, PR-551 km 2.7, gives `18.054444, -66.500278`.

The separation between these public coordinates demonstrates why the label `Cantera Naranjo` cannot be used as a shortcut to georegister an unlabeled screenshot. Facility points, quarry-property extents, extraction faces and cave locations are different spatial entities and must remain separate unless exact geometry establishes identity or containment.

## New historical-workings lead discovered during resolution

An official Puerto Rico historic-road guide describes `Cantera Naranjo` along PR-551 and states that the marble quarry contains tunnels from a manganese mine exploited in the early 1900s; it further states that most of those tunnels were destroyed by later quarry exploitation and that a small stone office building survives.

This is retained as `HISTORICAL_DOCUMENTARY_LEAD`, not as a screenshot binding and not yet as exact tunnel geometry. Before promotion it requires exact manifestation/identity binding between the guide's `Cantera Naranjo`, the frozen quarry manifestations, the cave/quarry property geometry and the relevant Santiago cell(s). The lead does not alter the `UNRESOLVED` state of either screenshot.

## Binding decision

### IMG_4020

- morphology: `GRADING_DISTURBANCE`
- visible subsurface indicator: `NONE_VISIBLE`
- coordinates in file metadata: none
- named landmark: none
- independent zone binding: not established
- final: `UNRESOLVED`

### IMG_4021

- morphology: `RURAL_RESIDENTIAL_AGRICULTURAL`
- visible subsurface indicator: `NONE_VISIBLE`
- coordinates in file metadata: none
- named landmark: none
- independent zone binding: not established
- final: `UNRESOLVED`

## Required evidence for future closure

Either image may be promoted from `UNRESOLVED` only if at least one of the following becomes available and independently checks against the frozen zone geometry:

- Google Earth coordinate readout at the image center or a visible target point;
- a named landmark, road kilometer marker, parcel/facility label, or uniquely identifying mapped feature visible in the viewport;
- a Google Earth project/KML placemark that records the screenshot center or selected-feature identity;
- another screenshot from the same uninterrupted viewport sequence containing a hard landmark and enough overlap to transfer the georegistration.

Until then, no SZ assignment is permitted.

## Model consequence

`IMG_4020.jpeg` and `IMG_4021.jpeg` remain outside all per-zone visual counts. The v1.1 relevance arithmetic remains unchanged: 146 total zones = 77 VERY_LOW | 62 LOW | 7 MODERATE | 0 HIGH.
