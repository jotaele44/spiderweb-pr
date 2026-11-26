# FED-GEO-SAR-001 — Geographic segmented acquisition and review

Preparation stage. This directory holds what was recovered from the three
repositories, the contracts proposed on top of it, and the evidence for each
preparation gate. **Nothing here is an implementation of the workbench.** The
one piece of running code is the durable job ledger, built in preparation
because its durability could not be measured any other way.

Status of the whole programme is in
[`D19_D20_BASELINE_AND_DOSSIER.md`](D19_D20_BASELINE_AND_DOSSIER.md). Read that
first.

## Deliverables

| ID | Deliverable | Where |
|---|---|---|
| D01 | Existing capability matrix | [`D01_D11_D12_CAPABILITY_AND_REUSE.md`](D01_D11_D12_CAPABILITY_AND_REUSE.md) |
| D02 | Internal geographic dataset register | [`D02_INTERNAL_DATASET_REGISTER.md`](D02_INTERNAL_DATASET_REGISTER.md) |
| D03 | Native asset ledger specification | [`D03_D06_LEDGER_SEGMENTATION_ACQUISITION.md`](D03_D06_LEDGER_SEGMENTATION_ACQUISITION.md) |
| D04 | Geographic segmentation contract | same file |
| D05 | Source discovery contract | same file |
| D06 | Acquisition requirement contract | same file |
| D07 | Comparison method registry | [`D07_D08_COMPARISON_AND_GAPS.md`](D07_D08_COMPARISON_AND_GAPS.md), `registry/geo_sar/comparison_methods.json` |
| D08 | Geographic gap registry contract | same file, `registry/geo_sar/gap_taxonomy.json` |
| D09 | Logical mosaic matrix contract | [`D09_D10_D13_GUI_AND_API.md`](D09_D10_D13_GUI_AND_API.md) |
| D10 | Split-view GUI specification | same file |
| D11 | Frontend component reuse matrix | [`D01_D11_D12_CAPABILITY_AND_REUSE.md`](D01_D11_D12_CAPABILITY_AND_REUSE.md) |
| D12 | Backend module reuse matrix | same file |
| D13 | Frontend/backend API contract | [`D09_D10_D13_GUI_AND_API.md`](D09_D10_D13_GUI_AND_API.md) |
| D14 | Federation responsibility matrix | [`D14_D15_RESPONSIBILITY_AND_SECURITY.md`](D14_D15_RESPONSIBILITY_AND_SECURITY.md) |
| D15 | Security and publication policy | same file |
| D16 | Persistent execution durability receipt | [`D16_DURABILITY_RECEIPT.md`](D16_DURABILITY_RECEIPT.md) |
| D17 | Pilot qualification suite | [`D17_PILOT_QUALIFICATION_SUITE.md`](D17_PILOT_QUALIFICATION_SUITE.md) |
| D18 | Dependency-directed implementation queue | [`D18_IMPLEMENTATION_QUEUE.md`](D18_IMPLEMENTATION_QUEUE.md) |
| D19 | Exact-head implementation baseline | [`D19_D20_BASELINE_AND_DOSSIER.md`](D19_D20_BASELINE_AND_DOSSIER.md) |
| D20 | Preparation qualification dossier | same file |

A decision record for where the workbench lives is in
[`ADR_WORKBENCH_SURFACE.md`](ADR_WORKBENCH_SURFACE.md).

## What exists in code

| Path | What it is |
|---|---|
| `spiderweb/geo_sar/jobs.py` | Durable job ledger (SQLite). Standard library only. |
| `spiderweb/geo_sar/handlers.py` | Local step handlers. None opens a network connection. |
| `scripts/geo_sar_worker.py` | Worker process that runs steps from the ledger. |
| `scripts/geo_sar_pilot_discovery.py` | Bounded, metadata-only discovery for the pilot extent, with offline replay. |
| `registry/geo_sar/` | Pilot asset ledger, comparison methods, gap taxonomy, pilot gaps. |
| `evidence/geo_sar/pilot_001/discovery/` | The 29 provider responses kept from the one live run, and its receipt. |
| `schemas/geo_sar_*.schema.json` | Schemas for the four registry files. |
| `tests/test_geo_sar_job_durability.py` | The ten mandatory durability tests. |
| `tests/test_geo_sar_pilot.py` | Pilot fixtures, discovery controls and offline replay. |

## Running it

```bash
python -m pytest tests/test_geo_sar_job_durability.py tests/test_geo_sar_pilot.py -q
```

```bash
python scripts/geo_sar_pilot_discovery.py replay
```

The live discovery run needs an explicit grant and refuses to overwrite the
kept run. It does not need to be run again.

## Reading the states

`PASS`, `PARTIAL`, `OPEN`, `BLOCKED`, `FAILED`, `UNVERIFIED`, `WITHHELD` and
`NOT_APPLICABLE` are used as in the directive. Claims are tagged `FACT` (read
from a file or a response), `COMPUTED` (derived by code in this repository),
`INFERENCE` or `UNKNOWN`. A `PASS` always names its evidence.
