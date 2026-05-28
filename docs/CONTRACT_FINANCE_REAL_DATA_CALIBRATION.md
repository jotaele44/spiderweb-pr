# Contract-Finance Real Data Calibration Notes

Calibration source files used for the first real-data pass:

| Input | Rows | Columns | Role |
|---|---:|---:|---|
| `pr_contracts_master_v2(3).csv` | 10,081 | 30 | Contract master / vendor-level contract context |
| `pr_all_awards_master(1).csv` | 281,337 | 15 | Federal/award-level funding context |
| `lda_canonical_client_summary_all.csv` | 609 | 11 | Lobbying/client context for later entity-resolution enrichment |

## Coverage read

| Field family | Finding | Engine consequence |
|---|---|---|
| Contract amount | `amount_usd` is populated for all 10,081 contract rows. | Strong for amount-weight calibration. |
| Contract dates | `award_date` and `fiscal_year` are populated for ~99.66% of contract rows. | Strong for temporal funding pulse calibration. |
| Award dates | `fiscal_year` is near complete, but `award_date` is partial. | Use fiscal-year fallback upstream when exact award date is missing. |
| Geometry | Uploaded masters do not expose `lat`/`lon` fields. | First production calibration should rely on municipality/entity/funding density until geocoded v1.1 package exports exist. |
| LDA overlap | Strict exact overlap is low under basic normalization. | Treat LDA as context until upstream fuzzy alias/entity-resolution promotes matches. |

## Amount profile

| Measure | Contracts `amount_usd` | Awards `obligated_amount` | LDA `total_lobbying_amount` |
|---|---:|---:|---:|
| Nonzero rows | 8,610 | 168,180 | 355 |
| Sum | $5.52B | $369.58B | $59.30M |
| P50 nonzero | $17,462 | $11,275 | $50,000 |
| P90 nonzero | $225,743 | $669,744 | $286,000 |
| P95 nonzero | $558,145 | $1.70M | $519,000 |
| P99 nonzero | $4.75M | $18.50M | $2.22M |
| Max | $1.15B | $34.30B | $7.66M |

## Recommended production gate posture

| Gate | Posture |
|---|---|
| `location_object_coverage` | Block below `0.50`. |
| `municipality_coverage` | Block below `0.25`; warn below `0.50`. |
| `point_geometry_coverage` | Warn below `0.05`; do not block first production pass. |
| `lineage_coverage` | Block below `0.25`; target `>=0.80`. |

## Calibration decision

The first production-ready SpiderWeb contract-finance calibration should be **municipality/entity-density first**, not point-geometry first. Point geometry can be promoted once Contract-Sweeper emits geocoded v1.1 packages with sufficient `location.lat` / `location.lon` coverage.
