# Decision record — where the comparison workbench lives

| | |
|---|---|
| Status | **PROPOSED.** Owner preference recorded; not ratified. |
| Date | 2026-11-26 |
| Scope | FED-GEO-SAR-001 |

## Context

The directive places the split-view comparison workbench and the logical
mosaic matrix in this repository, reusing its renderer and components. The
Federation's draft analytical workbench proposal assigns shared rendering
contracts to this repository as well.

Against that, `README.md` states that this repository's application is a
diagnostic-only surface under Federation decision record 0001, and that the
supported product interface is thehub-pr's application. That record lives in
thehub-pr; this repository cannot amend it.

## Decision proposed

Build the workbench in `server/frontend` of this repository.

Asked on 2026-11-26, the repository owner chose this over building it in
thehub-pr or leaving the question open.

## Why

- Every viewer component the workbench reuses is here (D11). None exists in
  thehub-pr.
- The asset ledger, segments and job ledger it reads are here.
- thehub-pr pins older renderer versions; building there means porting the
  viewer or moving the pin first.

## What it costs

- A standing Federation rule has to change, in thehub-pr.
- The application here has no authentication because it serves the local
  machine only. A product surface that accepts acquisition requests makes
  that assumption load-bearing (D15).
- Two applications in the Federation will then render maps on different
  renderer versions until E03 in D18 is settled.

## Until ratified

- `README.md` is left as it is. It remains true: nothing has been built.
- D18 item Q04 blocks the interface items that depend on this.
- If thehub-pr declines the amendment, D10 stands as a specification and the
  component list moves to thehub-pr with the port as an added first step.
