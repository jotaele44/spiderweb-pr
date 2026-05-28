# Federation Readiness

Checklist for promoting a `spiderweb-pr` export package from `mode=test` to
`mode=production`. The validator enforces the mode boundary mechanically; this
document is the operational checklist that has to pass *before* the producer
stamps `mode: "production"` in a manifest.

## Hard gates (validator-enforced)

These are checked by `scripts/validate_export.py --mode production` and fail
the package automatically. Confirm they pass before publish:

- [ ] No row in any stream has `is_synthetic: true`.
- [ ] Every row has a non-empty `source_id`, `lineage`, `confidence`, and the stream-appropriate timestamp.
- [ ] Every timestamp is ISO-8601 with timezone.
- [ ] Every geometry has coordinates in valid lat/lon range.
- [ ] Every stored row `id` matches `compute_row_id(row)`.
- [ ] The manifest declares all four streams with correct sha256 and record_count.
- [ ] The manifest `package_id` matches the recomputed sha256.

Run:

```bash
python scripts/validate_export.py --package <dir> --mode production
```

and expect exit code 0.

## Soft gates (operational checklist)

These are not enforced by the validator but should be reviewed by the operator
publishing the package:

- [ ] All upstream pipeline readiness reports in `readiness/` are green for the
      time window covered by `manifest.time_range`.
- [ ] OCR-derived observations have `confidence.method ∈ {ocr_consensus, manifest_attested, human_review}` —
      no raw single-engine OCR in production.
- [ ] Sources of kind `manual` have a `human_review` step in their lineage.
- [ ] `producer_version` is a clean git tag (not a dirty working tree).
- [ ] The package has been validated by a downstream consumer in a staging
      environment before promotion to production.

## Promotion process

1. Build the package with the producer's live data: `python scripts/build_export_package.py --out /tmp/pkg --mode production`.
   (The builder accepts `--mode production`; it will not strip synthetic rows,
   so the upstream pipeline must already exclude them.)
2. Run `python scripts/validate_export.py --package /tmp/pkg --mode production`.
3. Review the operational checklist above.
4. Publish.

## Demotion process

If a published production package is found to contain bad data:

1. Pull / withdraw the package from the federation hub.
2. Reproduce the package in `mode=test` locally.
3. Identify the offending lineage step(s) and fix in the upstream pipeline.
4. Republish, with a higher `producer_version`, after rerunning all gates.
