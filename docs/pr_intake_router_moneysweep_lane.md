# PR Intake Router — moneysweep-pr Lane

## Active vector
`MONEYSWEEP_POLITICS_FINANCE_UPDATE_LANE`

## Purpose
This document defines the moneysweep-pr side of the shared Puerto Rico intake router. moneysweep-pr is the canonical repository for politics, finance, procurement, public-funding, contracts, lobbying, budget authority, and public-execution-chain records.

The shared router should ingest Puerto Rico-relevant raw items once, classify the topic domain, assign canonical ownership, and then write only the correct derivative records into moneysweep-pr.

## Canonical ownership
moneysweep-pr owns records when the primary signal is one or more of:

- public funds
- budget authority
- fiscal policy
- procurement
- contracts or subcontracting
- grants, awards, obligations, reimbursements, allocations, transfers, disbursements
- lobbying or political influence
- agency authority or interagency agreements
- municipal finance
- public corporation finance or governance
- contractor / recipient / beneficiary chains

## Route to moneysweep-pr
A raw item should be routed here when any of these fields are detected:

| Signal | Examples | Canonical action |
|---|---|---|
| Funding amount | `$`, `millones`, `asignación`, `obligación`, `reembolso`, `inversión` | Create or update `funding_event_leads` |
| Contract/procurement | RFP, RFQ, subasta, aviso de adjudicación, amendment, contract number | Create or update `contracts_procurement_events` |
| Agency authority | executive order, budget certification, fiscal plan, board action, interagency agreement | Create or update `agency_actions` |
| Municipal finance | municipal project funds, transfer, resolution, local matching funds | Create or update `municipal_finance_events` |
| Political/lobbying link | lobbyist, donor, appointment, public board, politically exposed entity | Create or update `lobbying_political_links` |
| T1 confirmation | COR3, FEMA, OpenFEMA, OCPR, ASG, OGP, Hacienda, NEPR, HUD/CDBG | Create or update `t1_matches` |

## Do not make canonical here
Do not make moneysweep-pr canonical for records that are primarily:

- GIS / map / dataset / spatial layer
- terrain, hydrography, karst, geology, LiDAR, DEM, bathymetry
- aviation, maritime, federal/military operational movement without a funding or procurement angle
- weather, science, environment, monitoring data, alerts, field observations without grant/funding/procurement metadata

For those, route to spiderweb-pr. If the same item has fiscal data, create a backlink rather than duplicating the spatial record.

## Dual-route rules

| Input class | Canonical repo | moneysweep-pr record | spiderweb-pr derivative |
|---|---|---|---|
| Infrastructure funding announcement | moneysweep-pr | funding lead / project / award | POI/AOI/project footprint if location exists |
| Environmental grant | moneysweep-pr | award / funding event | dataset/site layer if spatial data exists |
| Road/bridge contract | moneysweep-pr | contract/procurement event | infrastructure asset or corridor candidate |
| USACE project notice with amount | moneysweep-pr | funding/procurement/agency action | federal infrastructure AOI |
| LUMA/Genera project with FEMA/PREPA/NEPR funding | moneysweep-pr | funding/procurement lead | grid asset if location exists |

## Required normalized fields

Every moneysweep-pr derivative record must preserve:

- `record_id`
- `source_item_id`
- `canonical_repo = moneysweep-pr`
- `related_repo_record_id`
- `source_name`
- `source_url`
- `published_at`
- `discovered_at`
- `agency_entity`
- `municipality_name`
- `municipality_geoid`
- `program_name`
- `funding_source`
- `amount_text`
- `amount_numeric`
- `action_type`
- `contract_number`
- `award_id`
- `prime_vendor`
- `subcontractor`
- `recipient_beneficiary`
- `asset_or_project_name`
- `asset_type`
- `evidence_tier`
- `confidence_level`
- `verification_status`
- `matched_t1_record_url`
- `link_confidence`
- `chain_id`
- `source_hash`
- `content_hash`
- `dedupe_group_id`
- `review_reason`

## Zero-loss status logic
Every observed item must receive exactly one final intake status:

- `routed_moneysweep`
- `routed_spiderweb_pr`
- `dual_routed_contract_primary`
- `dual_routed_spiderweb_primary`
- `duplicate_consolidated`
- `not_relevant_with_reason`
- `manual_review_required`
- `source_inaccessible`
- `blocked_or_paywalled`
- `metadata_only_archived`

No item may disappear between raw intake and normalized output.

## Validation gates

- No T2/T3 item may be marked `confirmed` without a matched T1 source.
- Every funding event must preserve original text amount and normalized numeric amount when parseable.
- Every cross-repo derivative must include `canonical_repo` and `related_repo_record_id`.
- Every dedupe merge must preserve all source URLs.
- Production mode must fail loudly if required source registry, dedupe keys, or schema fields are missing.

## Outputs

- `data/normalized/politics_finance_items.csv`
- `data/normalized/funding_event_leads.csv`
- `data/normalized/contracts_procurement_events.csv`
- `data/review/verification_queue.csv`
- `data/review/discrepancy_queue.csv`
- `data/exports/moneysweep_crosswalk_queue.csv`
- `reports/weekly/politics_finance_update_report.md`

## Next execution string
```text
EXECUTE_NEXT_VECTOR: IMPLEMENT_MONEYSWEEP_POLITICS_FINANCE_LANE → ADD_DOMAIN_ROUTER → ADD_POLITICS_FINANCE_TABLES → WIRE_FUNDING+PROCUREMENT+LOBBYING_CLASSIFIERS → ADD_T1_VERIFICATION_QUEUE → EXPORT_MONEYSWEEP_CROSSWALK_REPORT
```