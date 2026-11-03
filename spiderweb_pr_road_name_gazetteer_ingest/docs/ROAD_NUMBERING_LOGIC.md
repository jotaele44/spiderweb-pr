# Puerto Rico road-numbering logic

What a Puerto Rico route number tells the gazetteer, and what it does not.
The code that applies these rules is in `pipeline/road_gazetteer_ingest.py`.

## Number bands

| Band (`route_number_band`) | Numbers | Layout |
|---|---|---|
| `primary_band` | 1–99 | Main links between regions. No geographic pattern in the numbers. |
| `secondary_band` | 100–299 | Join municipios to the primary network. Laid out roughly as a grid: PR-100 is in the southwest and numbers rise toward the northeast. |
| `tertiary_band` | 300–9999 | Local and rural network. Published sources disagree on the upper limit (999 or 9999); the ingest uses 9999. |
| `unknown` | anything else, or no number | |

The bounds live in `ROUTE_NUMBER_BANDS`. If DTOP/ACT data shows different cut-offs, change them there.

## A band is not a network class

A route keeps its number for its whole length, but its *network* (primary, urban primary, secondary, tertiary) can change depending on the area it passes through. So:

- `route_number_band` comes only from the number. It never overwrites `road_class`, which is whatever the source declares.
- When a DTOP row's declared network differs from its band, the ingest records a `ROUTE_BAND_CLASS_DIVERGENCE` conflict at **LOW** severity. Treat it as a cue to review the row, not as an error. It is checked only for DTOP (T1) rows, because TIGER `RTTYP` and OSM `fclass` don't use DTOP network names.

## Suffixes and ramales

- A letter after the number is kept in `route_number` (`3R`) and also stored in `route_suffix` (`R`).
- `R` stands for *ramal*: a branch or loop of the base route, often through a town centre. PR-2 has several. `is_ramal` is true for these rows.
- `PR-3` and `PR-3R` are related but separate routes. The suffix stays in `route_number`, so name-variance conflicts never group a ramal with its parent route.
- Ramal rows also get `Ramal <n>` and `PR-<n> Ramal` aliases.

## Kilometre markers

Locations along a route are given as a kilometre marker counted from the route's origin, sometimes with hectometres: `Carr. 3 Km 5 Hm 2` = km 5.2. `km_marker_from_text` parses these, and `parse_route_ref` returns them as `km`. The canonical feature table doesn't store them, because they describe a point on a road rather than the road itself. They are there for consumers that resolve free-text locations.

## Recognised spellings

`route_number_from_text` / `ROUTE_PATTERNS` accept `PR-n`, `PR n`, `P.R. n`, `Puerto Rico Highway/Hwy/Route n`, `Carretera [Estatal] n`, `Carr. n`, `Ruta n`, and `n PR`.

## Source precedence

DTOP/ACT route data (T1) > Census TIGER (T2) > OSM (T3). OSM is used only for aliases and context; see `ROAD_GAZETTEER_INGEST_RUNBOOK.md`.

## Use by other federation repos

skywatcher-pr (OCR label classification) and ovnis-pr (free-text case locations) should use the exported `road_canonical_features.csv` / `road_feature_names.csv` columns, or call `parse_route_ref`, instead of copying these rules.

## Sources

- <https://en.wikipedia.org/wiki/List_of_highways_in_Puerto_Rico>
- <https://en.wikipedia.org/wiki/1953_Puerto_Rico_highway_renumbering>
- <https://wiki.aaroads.com/wiki/Roads_in_Puerto_Rico>
