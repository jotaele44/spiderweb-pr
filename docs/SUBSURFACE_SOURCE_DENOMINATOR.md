# Spiderweb Subsurface Public-Source Denominator v0.1

This document describes the source-control boundary implemented by `spiderweb.subsurface.sources`, `preflight`, `adapters`, and `runner`.

## Certification rule

A layer family is `PASS` only when **every required source manifestation** in that family has a terminal `PASS` or `ZERO` run receipt. `ZERO` is valid only after the registered query completes and its count/pagination arithmetic closes. `OPEN`, `NOT_RUN`, reference-only, unavailable, discovery-only, or malformed-service states are never negative evidence.

## Frozen queryable manifestations

| Family | Public manifestation | Role |
|---|---|---|
| GEOLOGY_KARST_CAVES | PR Planning Board Geologia 3; Sumideros 4; Valor Ecologico Cuevas 31 | supporting/direct |
| AQUIFERS_WELLS_SPRINGS | PRPB Acuifero 2; Manantiales 19; Pozos JCA 20; Pozo AAA 21; USGS Water Data OGC monitoring locations | supporting/direct |
| MINES_QUARRIES_SHAFTS | PRPB Calidad Ambiente Canteras 10 | direct quarry manifestation |
| MILITARY_HARDENED_SUBSURFACE | PRPB Guardia Nacional 4; USACE FUDS projects/MRS/properties | discovery only |
| INDUSTRIAL_REMEDIATION | PRPB UST 7; RCRA 13; Superfund 17; EPA NPL 30 | direct/supporting |
| UTILITIES_UNDERGROUND | PRPB wastewater pumps 5; AAA Linea Matriz 3; sewer gravity 5; force main 6 | supporting/direct |

## Authoritative references still requiring exact payload binding

- USGS Karst Map of Puerto Rico OFR 2010-1104 GIS archive.
- USGS neotectonic Puerto Rico data release P13KZZAZ.
- USGS NSHM 2025 Puerto Rico/USVI earthquake-geology inputs P9ONHNOD.
- USGS Great Southern Puerto Rico Fault Zone data release P18SPREU.
- USGS MRDS Puerto Rico industrial-mineral mine/prospect/occurrence records and OFR 92-244 / 98-038 manifestations.
- EPA Envirofacts FRS/RCRAInfo/SEMS table and query denominator.
- USGS historical geologic-map catalog manifestations and historical aerial/map temporal denominator.

## Explicit OPEN residue

The denominator intentionally retains OPEN rows for:

- exact shaft/adit geometry beyond quarry and mine/occurrence references;
- authoritative public hardened/underground military-asset identity (FUDS and tenure do not prove subsurface structures);
- non-AAA/private underground utility networks;
- historical aerial/map temporal coverage until exact collections and acquisition/query rules are frozen.

No FOIA/records-request route is implied by these OPEN rows. Public-source acquisition remains the controlling vector until its bounded sources are terminal.

## ArcGIS freeze contract

Before a layer query, Spiderweb snapshots the layer metadata and freezes the OID field, schema, geometry type, Z/M flags, spatial reference, maximum record count, supported query formats, and query contract. The AOI run then performs a count-first spatial query, freezes the count response, pages deterministically, freezes every raw page, computes byte and canonical-logical SHA-256 values, and verifies count/page/retained arithmetic.

## OGC freeze contract

OGC Features sources are queried by AOI bbox plus registered source filters. Every response page is frozen and hashed; `rel=next` is followed until absent; pagination cycles fail closed; `numberMatched` is reconciled when supplied.

## Identity boundary

A source manifestation is not a canonical entity. Planning Board, USGS, EPA, USACE, or other records that appear to describe the same real-world feature remain separate candidates until stable IDs or other independent binding evidence supports a 1:1, 1:N, N:1, or N:N resolution.
