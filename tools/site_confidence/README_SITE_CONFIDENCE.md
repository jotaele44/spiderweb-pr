# Site Confidence Module

Single-site geospatial confidence workflow for Puerto Rico candidate points.

## Target site

- `site_id`: `SITE_RI_20260522_001`
- `name`: Royal Isabela vegetated structure
- `lat`: `18.4878021`
- `lon`: `-66.9896910`
- `context`: partially canopy-obscured rectilinear structure near Royal Isabela golf-course/agricultural/service-road edge
- `source`: Flightradar24 screenshot over Apple Maps basemap
- `visible_timestamp`: `2026-05-22T19:47:00-04:00`

## Workflow

1. Create site record.
2. Generate AOI buffers at 250 m and 500 m.
3. Create LiDAR/DEM acquisition manifest.
4. Add evidence rows as layers become available.
5. Compute provisional or evidence-backed confidence score.
