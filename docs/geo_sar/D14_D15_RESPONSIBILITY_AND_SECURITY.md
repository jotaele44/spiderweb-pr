# D14, D15 — Federation responsibility matrix and security policy

## D14 — Responsibility matrix

| Repository | Authority | Recovered in this pass |
|---|---|---|
| spiderweb-pr | Geographic identities, segmentation, asset ledger, acquisition, generic geographic comparison | Yes |
| thehub-pr | Governance, execution admission, integrity, LOCKSTEP | Yes, read at `36a08974dda53c971c2283f019318e17a14d43df` |
| mucaro-ai | Research and execution orchestration | Yes, read at `13ad436668dbc26712ec53b163e64dcf972e16d0` |
| skywatcher-pr | Imagery and aviation interpretation, SATIM | **No.** Not attached to the session. |
| aguayluz-pr | Hydrology, environment, electrical evidence | No |
| moneysweep-pr | Financial and contractual relationships | No |
| centinelas-pr | Regulatory and institutional evidence | No |
| ovnis-pr | Historical case and observation evidence | No |

### Contracts this work must conform to

All in thehub-pr. Paths are relative to that repository.

| Contract | Path | Conformance today |
|---|---|---|
| Producer manifest and export package | `schemas/repo_federation_manifest.schema.json` | Existing `federation.json` unchanged |
| Identity | `schemas/contracts/federation_identifier.v1.schema.json` | Not yet bound: pilot asset identifiers are local |
| Evidence state, object, lineage | `schemas/federation/` | Not yet bound |
| Access classes | `schemas/contracts/access_classification.v1.schema.json` | Adopted in D15 below |
| Acquisition rules | `docs/GIS_ACQUISITION_V2.md` | Followed by the discovery contract (D05) |
| Grid authority pin | `federation/spatial/pr_grid_geographic_v2.pin.json` | Unchanged; segments are Grid V2 cells |
| Analytical workbench proposal | `docs/governance/FAWS_V0_1_PROPOSAL.md` | Draft there; assigns rendering contracts to this repository |
| Execution admission | `governance/ecpaf/v2.1/policy.json` | **No route.** See below. |
| LOCKSTEP bindings | `federation/lockstep-bindings.json` | Unchanged |
| Documentation sync | `.federation/docs-sync.json` | Checked on this change |

### What governance cannot yet do for this programme

1. **No admission route for an acquisition job.** thehub-pr's persistent
   executor admits only draft pull requests that change code. Its policy
   records certification as withheld. An acquisition job has nowhere to be
   admitted.
2. **mucaro-ai cannot run it either.** Its federation worker route is
   declared and raises "unavailable"; its durable lease queue is a library
   that only tests import.
3. **This repository now has its own ledger** (D16), by the owner's decision.
   That is a second execution mechanism in the Federation. It is kept behind
   one module so it can be replaced, and it follows the same rules as
   mucaro-ai's queue: leases, generation fencing, no automatic replay of an
   interrupted change. It is not governed by thehub-pr.
4. **No qualification receipt schema exists** in thehub-pr. Receipts produced
   here are local records, not Federation receipts.
5. **LOCKSTEP is weaker than its own rules.** The evaluator checks that a
   contract file exists on the default branch; it does not check current
   certification or exact heads. LOCKSTEP qualification of this work would
   therefore not mean what the binding file says it means.

### SATIM

The directive asks that the SATIM colour convention be preserved (red: seams
and artifacts; blue: water; yellow: earthworks). **That convention was not
found** in thehub-pr, mucaro-ai or this repository. thehub-pr holds a schema
for a provisional SATIM signal and this repository re-implements part of the
specification in `spiderweb/site_timeline/`. The convention presumably lives
in skywatcher-pr, which was not available. The annotation contract is
therefore `BLOCKED` on attaching that repository; it was not reconstructed
from the directive's description.

## D15 — Security and publication policy

### Controls and their state

| Control | State | Where |
|---|---|---|
| Destination admission (hosts, scheme) | PASS for pilot discovery | `scripts/geo_sar_pilot_discovery.py`, tested |
| Server-side request forgery | PASS for pilot discovery: only two literal hosts, no redirects, no credentials in addresses, default port only. **Not general**: other fetch paths use an unrestricted opener | `scripts/location_query_fetch.py` and the adapter kit under `scripts/source_adapters/sdk/` have no allow-list |
| Archive extraction | **OPEN defect** | `scripts/source_adapters/census_partnership_pr/normalize.py` and `scripts/source_adapters/pr_hydrography/certify_historical_snapshot.py` call `extractall` without checking member paths |
| Path traversal | PASS for the ledger handler | Destination joined with `pipeline/path_safety.py`; tested indirectly |
| Download size limits | PASS at the ledger: byte ceiling and file count checked before a step runs | `test_06_authorization_boundaries_remain_enforced` |
| Content-type validation | OPEN | Not implemented |
| Checksum verification | PASS for local steps | `test_09_terminal_failures_are_accurately_reported` |
| Source revision detection | PARTIAL | Object tag and last-modified time are recorded per file; nothing compares them yet |
| Quarantine | OPEN | A failed artifact is deleted, not quarantined |
| Database migration integrity | PARTIAL | The ledger refuses to open a file with another schema version; no migration path |
| Transaction recovery | PASS | Every write is one immediate transaction; kill tests in D16 |
| Authorisation boundaries | PASS at the ledger | D16 test 06 |
| Sensitive locations | Policy below; nothing enforces it yet | — |
| Licensing and redistribution | `UNVERIFIED` for every asset | — |
| Audit receipts | PASS | Append-only events; kept provider responses |
| Exact head and configuration | PASS for this pass | D19 |

The two archive defects and the unrestricted fetch paths are **mandatory
fixes before any acquisition beyond the pilot**. They are first in D18.

### Publication policy

- Every asset and observation carries one of thehub-pr's access classes.
  Default for public provider data is `PUBLIC`.
- A location that identifies sensitive infrastructure, private property or a
  protected natural resource is classed `SENSITIVE_LOCATION`. It stays in the
  local store, is excluded from Federation export, and is not sent to an
  external model. thehub-pr already treats this class as high risk for model
  egress.
- An absent record is never published as a finding about the ground.
- Provider bytes are not committed, with one exception made here: the first
  64 KiB of each pilot file and one catalogue response (2.0 MB in total), kept
  so that the ledger can be rebuilt and checked offline. These are United
  States Geological Survey products; their licence status is recorded as
  `UNVERIFIED` until confirmed, which is a gap, not an assumption of
  restriction.
- The live discovery sent no repository, project or operator name. The user
  agent was generic.

### Assumptions that must stay true

- The API binds to the local machine only and has no authentication. Any
  deployment that changes the first must add the second before the `/geo-sar`
  write routes exist.
- The ledger file is trusted local state. Someone who can write the file can
  change a grant; the API offers no way to do so.
