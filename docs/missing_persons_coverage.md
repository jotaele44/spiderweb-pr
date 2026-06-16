# Missing-persons coverage matrix

This doc is the human-readable companion to
`configs/missing_persons_sources.yaml`. The YAML is the source of truth; this
doc is a checked-in snapshot of "where are we today" so reviewers can spot
gaps without parsing YAML.

If you change `configs/missing_persons_sources.yaml`, update this doc in the
same PR. The audit (`tools/pr_geodata_integrity_audit.py:audit_missing_persons_coverage`)
flags drift between YAML reality and the matrix below indirectly by reporting
class-coverage gaps.

**Last reconciled with YAML**: 2026-06-12 (phase 2c.2 — PRPB Desaparecidos gallery landed).

---

## Coverage by incident class

Each cell shows the source's `status` in the YAML registry. `🟢 landed` means
the harvester is shipping and the audit found a snapshot. `🟡 planned` means
the row is wired in the registry but the harvester hasn't been built yet.
`🔵 aggregate_only` and `🟠 manual_pull` mean structural limits (see §3 of the
v2 plan). `⚫ cannot_reach` is reserved for hard blocks (LE-only, paywall).

| Incident class | Federal (NamUs / NCIC / NCMEC / USCG) | PR Commonwealth | Cross-border (IOM / Interpol / ICRC) | NGO / Journalism | Tip-stream | Backfill |
|---|---|---|---|---|---|---|
| `missing_juvenile` | NamUs 🟢 · NCMEC 🔵 · NCIC 🔵 | **PRPB Desaparecidos 🟢** · **Plan AMBER 🟢** · Power BI 🟡 · DSP 🟡 | — | — | FB PersonasDesaparecidasPR 🟡 · FB Búsqueda PR 🟡 | — |
| `missing_adult_woman` | NamUs 🟢 · NCIC 🔵 | **PRPB Desaparecidos 🟢** · Power BI 🟡 · DSP 🟡 | — | Observatorio EEG 🟡 · CPI Género 🟡 · Diaspora 🟡 | FB groups 🟡 | — |
| `missing_adult_other` | NamUs 🟢 · NCIC 🔵 · USCG D7 🟠 | **PRPB Desaparecidos 🟢** · Power BI 🟡 · DSP 🟡 | ICRC 🔵 | — | FB groups 🟡 | — |
| `endangered_woman` | NCIC 🔵 | **Plan ROSA 🟢** | — | Observatorio EEG 🟡 · Proyecto Matria 🟡 · Inter News 🟡 · CPI Género 🟡 · Diaspora 🟡 | — | — |
| `cognitive_impairment` | NCIC 🔵 · HHS ACL 🔵 | **Plan SILVER 🟢** · Familia 🟠 | — | — | — | — |
| `endangered_adult` | NCIC 🔵 | **Plan ASHANTI 🟢** · Familia 🟠 | — | — | — | — |
| `maritime` | USCG D7 🟠 | — | IOM Missing Migrants 🟡 · ICRC Caribbean 🔵 | — | — | — |
| `disaster` | FEMA reports 🔵 | NMEAD 🟡 | — | — | — | María 🟡 · Fiona 🟡 · 2020 SW earthquake 🟡 |
| `unidentified_remains` | NamUs Unidentified 🟡 | ICF 🟡 · Registro Demográfico 🟡 | — | — | — | — |
| `unclaimed_decedent` | NamUs Unclaimed 🟡 | Registro Demográfico 🟡 | — | — | — | — |
| `international_missing` | — | — | Interpol Yellow (OpenSanctions) 🟡 | — | — | — |

**Today's reality (post-2c.2)**: 6 of 11 incident classes have ≥1 landed
harvester. PRPB Desaparecidos landing doesn't add new classes (the 3 classes
it covers — juvenile, adult_woman, adult_other — were already on NamUs) but
it makes the per-municipio aggregate **dense** for the first time: NamUs's
~200/yr PR rows are sparse, PRPB Desaparecidos's ~3,000/yr fills out every
municipio. The audit still WARNs on 5 uncovered classes: `maritime`,
`disaster`, `unidentified_remains`, `unclaimed_decedent`,
`international_missing`. Those land in phases 2b, 2d, and 2g.

---

## Coverage by source (status by phase)

| Phase | Source | Status | Federation eligible | Stratum | Expected PR yield / yr |
|---|---|---|---|---|---|
| **1 (landed)** | `namus` | 🟢 harvester_landed | aggregate_only | A | 200 |
| **2c.1 (landed)** | `prpb_alertas_amber` | 🟢 harvester_landed | aggregate_only | A | 15 |
| 2c.1 (landed) | `prpb_alertas_rosa` | 🟢 harvester_landed | aggregate_only | A | 30 |
| 2c.1 (landed) | `prpb_alertas_silver` | 🟢 harvester_landed | aggregate_only | A | 80 |
| 2c.1 (landed) | `prpb_alertas_ashanti` | 🟢 harvester_landed | aggregate_only | A | 40 |
| **2c.2 (landed)** | `prpb_desaparecidos` | 🟢 harvester_landed | false (ToS unclear, raw PII) | A | 3,000 |
| **2c.3** | `prpb_powerbi_aggregate` | 🟡 planned | aggregate_only | A | 0 (counts) |
| 2c.3 | `dsp_aggregate` | 🟡 planned | aggregate_only | A | 0 (counts) |
| **2b** (federation + 2 cleanest sources) | `iom_missing_migrants` | 🟡 planned | true | A | 30 |
| 2b | `interpol_yellow` | 🟡 planned | aggregate_only | A | 5 |
| 2b | `icrc_caribbean` | 🔵 aggregate_only | aggregate_only | A | 0 |
| **2d** (unidentified loop) | `namus_unidentified` | 🟡 planned | aggregate_only | A | 40 |
| 2d | `namus_unclaimed` | 🟡 planned | aggregate_only | A | 20 |
| 2d | `icf_unidentified` | 🟡 planned | aggregate_only | A | 30 |
| 2d | `registro_demografico_aggregate` | 🟡 planned | aggregate_only | A | 0 |
| 2d | `ncic_aggregate` | 🔵 aggregate_only | aggregate_only | A | 0 |
| **2e** (journalism / NGO) | `observatorio_eeg` | 🟡 planned | aggregate_only | B | 50 |
| 2e | `proyecto_matria` | 🟡 planned | aggregate_only | B | 30 |
| 2e | `inter_news_femicide` | 🟡 planned | aggregate_only | B | 25 |
| 2e | `cpi_genero` | 🟡 planned | aggregate_only | B | 15 |
| 2e | `diaspora_news` | 🟡 planned | aggregate_only | B | 10 |
| **2f** (tip-stream, stratum C) | `fb_personasdesaparecidaspr` | 🟡 planned | **false** | **C** | 500 |
| 2f | `fb_busquedapr` | 🟡 planned | **false** | **C** | 300 |
| **2g** (historical backfill) | `gwu_maria_mortality_study` | 🟡 planned | aggregate_only | B | one-shot |
| 2g | `quartz_maria_dataset` | 🟡 planned | aggregate_only | B | one-shot |
| 2g | `backfill_fiona_2022` | 🟡 planned | aggregate_only | A | one-shot |
| 2g | `backfill_earthquake_2020_sw` | 🟡 planned | aggregate_only | A | one-shot |
| 2g | `nmead_disaster` | 🟡 planned | aggregate_only | A | event-driven |
| **deferred** (FOIA / closed access) | `ncmec_aggregate` | 🔵 aggregate_only | aggregate_only | A | 0 |
| deferred | `uscg_d7_sar` | 🟠 manual_pull | aggregate_only | A | 60 |
| deferred | `departamento_familia_aggregate` | 🟠 manual_pull | aggregate_only | A | 0 |

---

## Hard limits ("100%" ceiling is real)

These are the cells in the matrix that no engineering work closes; documenting
them so "covered" never silently means "we forgot":

- **NCIC raw case-level**: ⚫ cannot_reach. Federal statute restricts to LE
  agencies. Aggregate counts only.
- **PRPB Desaparecidos federation**: federation_eligible = false. Page shows
  names + photos; redistributing per-case in a federated graph would re-leak
  PII even after our redaction. Workbench only.
- **Stratum C (FB groups)**: federation_eligible = false in registry, enforced
  by the consolidator hard-coding the boundary. Used only for the
  tipstream-vs-confirmed under-reporting heatmap.
- **Structural under-reporting**: Afro-Boricua cases, undocumented migrants,
  sex workers, trans persons, LGBTQ+ youth. Every source we surveyed
  under-reports these populations; this is a coverage gap no harvester
  closes. The coverage audit's `tipstream_vs_confirmed` gap layer (phase 2f)
  is the closest engineering proxy.

---

## What the audit checks against this doc

`tools/pr_geodata_integrity_audit.py:audit_missing_persons_coverage` reads
`configs/missing_persons_sources.yaml` and emits findings for:

- `registry_loadable` — YAML parses + has `version`
- `landed_sources_present` — at least one harvester is shipping
- `class_coverage` — every declared incident_class has ≥1 landed source
- `snapshot_present` — landed sources have a dated snapshot subdir
- `snapshot_freshness` — latest snapshot age ≤ 2× `refresh_cadence_days`
- `yield_band` — row count within ±50% of `expected_pr_yield_per_year` prorated
- `stratum_federation_consistency` — stratum C is never federation-eligible
- `disaster_event_id_valid` — references to `disaster_event_id` exist in the
  events registry

All findings WARN-only; the gate remains GO/CONDITIONAL_GO for sparse coverage.
