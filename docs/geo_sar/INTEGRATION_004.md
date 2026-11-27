# INTEGRATION-004 — bounded read-only pilot
Base: 4f5a3f1e50e335e17814dad4780a49573bbdd094.

ADR 0014 supersedes the diagnostic-only restriction in ADR 0001. Spiderweb may
host its domain workbench; cross-producer views remain Hub-owned. GUI parity
and token rules still apply. This supersedes the policy blocker in the older
GEO-SAR workbench ADR, not its other admission conditions.

The AOI branch is 42 commits ahead and 606 behind this base; no wholesale merge
is attempted. The new read-only endpoint GET /geo-sar/context?bbox=w,s,e,n
returns a bounded pilot ledger revision, geographic context, distinct dataset
versions, intersecting native assets, unresolved and touch-only counts.
Footprint intersections are computed from densified native extents transformed
to WGS84; they do not establish valid-data coverage. Segment binding remains
unverified. No acquisition or comparison qualification is authorized by this
endpoint. Both panels reuse the existing spatial runtime; maps are reference
basemaps, not acquired source imagery. No synthetic availability is displayed.

Map hash writers preserve bearing/pitch and unrelated keys; full single-writer
refactor remains open. SATIM annotation profiles remain separate and unimplemented.
Federation GUI manifest/parity registration remains open. No live download,
persistent supervisor, or production certification is claimed.

Local baseline replay test fails on unchanged main as well as this candidate;
the frozen ledger is preserved. Root cause unverified.
