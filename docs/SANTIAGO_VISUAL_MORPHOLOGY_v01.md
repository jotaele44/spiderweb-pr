# Santiago Triangle — Visual Morphology Falsification Layer v0.1

## Scope

This layer records a user-supplied Google Earth screenshot corpus as a **visual falsification/context surface** for the eight original v1 MODERATE Santiago cells. Raw screenshots are not committed to the repository. Only image SHA256 identifiers, zone-binding state, morphology class, and bounded interpretation are retained in the derived assessment manifest.

Visual morphology has **zero score effect** and can never promote a zone, establish identity, infer connectivity, or convert a surface excavation into a portal/shaft/tunnel finding.

## Hard rules

- `promotion_permitted = false` for every image assessment.
- Ambiguous viewport-to-zone bindings remain `UNRESOLVED`.
- Surface quarrying/grading is not direct underground-opening evidence.
- Urban/industrial/institutional density is not subsurface evidence.
- UI notifications and unrelated personal interface content are ignored and are not carried into the evidence pack.
- No raw screenshot bytes are committed.

## Screenshot adjudication

Fifteen screenshots were frozen locally by SHA256. Thirteen receive a bounded contextual/landmark zone binding; two remain unbound.

| Screenshot | Zone | Binding | Morphology | Visible subsurface indicator |
|---|---|---|---|---|
| `IMG_4018.jpeg` | SZ-0018 | STRONG_CONTEXTUAL | RURAL_AGRICULTURAL_FOREST | NONE_VISIBLE |
| `IMG_4019.jpeg` | SZ-0018 | STRONG_CONTEXTUAL | RURAL_INSTITUTIONAL_COMPOUND | NONE_VISIBLE |
| `IMG_4020.jpeg` | — | UNRESOLVED | GRADING_DISTURBANCE | NONE_VISIBLE |
| `IMG_4021.jpeg` | — | UNRESOLVED | RURAL_RESIDENTIAL_AGRICULTURAL | NONE_VISIBLE |
| `IMG_4022.jpeg` | SZ-0015 | CANDIDATE | SURFACE_QUARRY | SURFACE_EXTRACTION_ONLY |
| `IMG_4023.jpeg` | SZ-0006 | STRONG_CONTEXTUAL | PERIURBAN_TRANSPORT_RESIDENTIAL | NONE_VISIBLE |
| `IMG_4024.jpeg` | SZ-0006 | AUTHORITATIVE_LANDMARK | INSTITUTIONAL_SCHOOL_TRANSPORT | NONE_VISIBLE |
| `IMG_4025.jpeg` | SZ-0041 | AUTHORITATIVE_LANDMARK | URBAN_MIXED | NONE_VISIBLE |
| `IMG_4026.jpeg` | SZ-0040 | STRONG_CONTEXTUAL | AGRICULTURAL_RIPARIAN | NONE_VISIBLE |
| `IMG_4027.jpeg` | SZ-0083 | AUTHORITATIVE_LANDMARK | URBAN_MOUNTAIN | NONE_VISIBLE |
| `IMG_4027(1).jpeg` | SZ-0083 | AUTHORITATIVE_LANDMARK | URBAN_MOUNTAIN | NONE_VISIBLE |
| `IMG_4028.jpeg` | SZ-0074 | STRONG_CONTEXTUAL | RURAL_COMPOUND_SURFACE_WATER | NONE_VISIBLE |
| `IMG_4029.jpeg` | SZ-0074 | STRONG_CONTEXTUAL | RURAL_STRUCTURE_VEGETATED | NONE_VISIBLE |
| `IMG_4030.jpeg` | SZ-0083 | AUTHORITATIVE_LANDMARK | INDUSTRIAL_COMPLEX | NONE_VISIBLE |
| `IMG_4031.jpeg` | SZ-0083 | AUTHORITATIVE_LANDMARK | INDUSTRIAL_COMPLEX | NONE_VISIBLE |

## Binding notes

### SZ-0006
`IMG_4024.jpeg` contains the named Escuela Elemental Maria Ortiz. Its public plus-code location resolves inside the SZ-0006 bounds. The adjacent PR-52/developed context in `IMG_4023.jpeg` is retained as strong contextual corroboration only.

### SZ-0015
`IMG_4022.jpeg` clearly depicts a large exposed quarry/extraction landscape. It is only a **candidate visual binding** to SZ-0015 because public/frozen Cantera Naranjo manifestations contain coordinate/name inconsistencies. The morphology is surface extraction; no portal, shaft, or tunnel entrance is visible.

### SZ-0018
The named Finca Ganadería Rodríguez lies immediately east of the SZ-0018 eastern boundary. The white selected-feature boundary visible west of the named finca is consistent with that edge, so `IMG_4018.jpeg` and its close view `IMG_4019.jpeg` are strong contextual bindings rather than exact feature-identity bindings.

### SZ-0040 / SZ-0041
The Coamo screenshots separate naturally into the southern agricultural/riparian cell (SZ-0040) and the urban-core cell (SZ-0041). Neither supplies visible underground-opening evidence.

### SZ-0074 / SZ-0083
The Aibonito imagery separates the western Asomante/To Ricos context (SZ-0074) from the eastern Aibonito urban/industrial context (SZ-0083). Public To Ricos factory coordinates fall inside SZ-0074; Aibonito town and Baxter-Aibonito heliport coordinates fall inside SZ-0083. The industrial-complex morphology in `IMG_4030.jpeg`/`IMG_4031.jpeg` does not affect relevance score.

## Model consequence

The visual audit **does not change v1.1 arithmetic**:

- 146 zones
- 77 VERY_LOW
- 62 LOW
- 7 MODERATE
- 0 HIGH
- SZ-0015 remains ROBUST / DIRECT because of mapped cave evidence, not because of imagery.
- SZ-0006 remains SEMI_ROBUST.
- SZ-0083 remains PROVISIONAL and LOW after canonical deduplication.

The imagery mainly functions as a falsification check against over-reading busy surface landscapes. Surface quarrying, road cuts, ponds, factories, schools, hospitals, agricultural fields, and dense urban infrastructure all have ordinary surface explanations and are not promoted into subsurface claims.
