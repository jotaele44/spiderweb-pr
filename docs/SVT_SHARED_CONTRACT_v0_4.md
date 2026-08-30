# Spiderweb ↔ SVT shared execution contract v0.4

Spiderweb is the execution/control-plane layer. Subsurface Void Tracing (SVT) is the domain-reasoning layer. Both implementations share the following invariants.

- Manifestation status, run state, and exhaustion state are separate axes.
- Only executed `PASS|ZERO` manifestations are terminal for bounded public-source exhaustion.
- `FINAL_PUBLIC_GAP` is a bounded source-class conclusion and never permits negative evidence by itself.
- Source quality (`T1..T4`) is separate from evidence relationship (`DIRECT|SUPPORTING|CANDIDATE|CONTRADICTED|UNRESOLVED`).
- Spatial adjudication terminates as `FULLY_WITHIN|PARTIAL|TOUCH_ONLY|OUTSIDE|NULL_EMPTY|UNRESOLVED`.
- Canonical physical assets preserve source manifestations and carry `1:1|1:N|N:1|N:N|0:1|UNRESOLVED` cardinality.
- Proximity, nearest, name-only, same category/system, and shared provenance never bind identity alone.
- Shared provenance reduces independence; it is not corroboration.
- Relevance scoring uses capped/logarithmic density terms and does not create connectivity.
- Connectivity requires typed binding evidence (`SURVEYED_PASSAGE|TRACER_CONFIRMED|AS_BUILT_CONNECTION|HYDRAULIC_TEST|DOCUMENTED_TUNNEL_LINK`).

The portable SVT v0.4.0 package remains backward-readable for v0.3.1 artifacts and imports these semantics without importing Spiderweb-specific project ontology or source lists.
