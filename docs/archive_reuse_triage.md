# Archive Reuse Triage — Raw Data Drop Pattern

Plan for issue #38 (*Backlog: triage reusable Archive.zip planning assets*).

This is a **plan-only** document. It selects **one** ADAPT item from the backlog —
the **Raw data drop triage pattern** — and specifies how a future raw drop
(`Archive.zip` or any unreviewed bundle) should be handled. No code is added and
no archive content is imported by this document, per the issue's guardrails:

- No wholesale ZIP import.
- No confirmation semantics from planning notes.
- No unreviewed automation.
- Keep active code vectors narrow and source-backed.

## Why this item first

Of the five ADAPT candidates in #38, the raw-drop triage pattern is the
prerequisite for the others (FR24 screenshot ingest, anomaly intake rubric,
workbench architecture): each begins with *material arriving from outside the
repo*, and none should be ingested before classification. Establishing the
intake discipline once keeps every later vector source-backed.

## The pattern: manifest-first, hash-dedupe, explicit keep/drop

A raw drop is never ingested directly. It moves through four ordered gates; a
later gate runs only if the earlier gate passed.

1. **Manifest first.** Enumerate every entry in the drop (relative path, byte
   size, SHA-256) into a manifest **before** any file is read for content. No
   file is opened for ingestion until it appears in the manifest.
2. **Hash dedupe.** Compute a content hash per entry and drop entries whose hash
   already exists in the repo or earlier in the same drop. Dedupe is by content
   hash, not filename.
3. **Explicit keep/drop list.** Every manifest entry is classified into exactly
   one of `keep`, `drop`, or `needs-review`. Nothing is implicitly kept. The
   classification is recorded alongside the manifest so the decision is auditable.
4. **No ingestion before classification.** Only `keep` entries — after the list
   is reviewed — are eligible to be adapted into a narrow, source-backed vector.
   `needs-review` blocks; `drop` is discarded.

### Default drop list (from #38)

These categories are environment/agent-workspace artifacts and are dropped
unconditionally: `plugins/`, `backups/`, `cache/`, shell snapshots,
tasks/sessions/history files, MCP/auth/cache files, and user environment settings.

## Reuse existing conventions (do not reinvent)

The repo already has the building blocks this pattern needs; a future
implementation should reuse them rather than add parallel utilities:

- **Hashing** — `provenance_utils.compute_sha256(path)` for per-entry content
  hashes (gate 2).
- **Manifest provenance** — `provenance_utils.attach_to_manifest(...)` and
  `provenance_utils.reproducibility_metadata(...)` to stamp the manifest with
  git head, platform, and timestamps (gate 1).
- **Import guidance** — `server/docs/data_import_guide.md` for the existing
  data-import conventions any `keep` item must follow.

## Out of scope (tracked, not done here)

The remaining #38 ADAPT items stay in the backlog and are intentionally not
planned by this document:

- PR.INT workbench architecture (revisit after the FR24 temporal dashboard
  stabilizes).
- FR24 screenshot / HEIC ingest plan.
- Contract-Sweeper NGO / OSFL integration (belongs in Contract-Sweeper).
- Puerto Rico anomaly / UAP intake rubric (convergence only; no claim escalation
  without corroboration).

## Suggested next vector

```text
EXECUTE_NEXT_VECTOR: RAW_DROP_TRIAGE_PATTERN_ADOPTED → ON_NEXT_DROP:
  BUILD_MANIFEST(sha256) → HASH_DEDUPE → KEEP/DROP/NEEDS-REVIEW_LIST →
  REVIEW → ADAPT_ONLY_KEEP_ITEMS_SOURCE_BACKED
```
