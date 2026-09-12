# Federation Executable Surface Auditor — PoC Contract

## Purpose

Determine whether declared user-facing operations have sufficient evidence to be executable without treating visual presence, naming, proximity, or lexical discovery as proof of functionality. The auditor is intentionally side-effect-free: it may inspect source and produce evidence, but it does not import or invoke application handlers, API mutations, pipelines, external services, or domain features.

This Spiderweb implementation is a bounded proof-of-concept for the canonical Federation workflow. Canonical policy ownership should reside in the Federation hub; repository implementations remain bounded operational consumers.

## Evidence ladder

`PRESENT -> WIRED -> ROUTED -> DEPENDENCIES_RESOLVED -> CONFIGURABLE -> PRECONDITIONS_SATISFIABLE -> DRY_RUN_CAPABLE -> EXECUTABLE_PROVISIONAL -> EXECUTABLE_CONFIRMED`

A lower state never implies a higher state. In particular, `WIRED` means an authored control has a source-visible event binding; it does **not** mean its downstream action is executable.

Terminal/gap states include `DEAD_SURFACE`, `STUB`, `NONEXECUTABLE`, `BLOCKED`, and `UNRESOLVED`. `EXECUTABLE_CONFIRMED` requires controlled execution evidence and is outside this static PoC's claim.

## Side-effect policy

| Class | Audit behavior |
| --- | --- |
| SAFE_READ | May execute in later runtime phase |
| SAFE_LOCAL | May execute in isolated runtime phase |
| REVERSIBLE | Sandbox + rollback required |
| SANDBOXABLE | Sandbox required |
| EXTERNAL_MUTATION | Intercept; do not transmit |
| DESTRUCTIVE | Block |
| UNKNOWN | Block |

The current PoC assigns discovered controls `UNKNOWN_BLOCKED`; therefore it performs no target feature execution.

## Canonical pipeline

1. Freeze repository, commit, query/scope, retrieval time, and raw inputs.
2. Discover declared capability manifestations without semantic merging.
3. Construct a capability graph preserving all candidate edges.
4. Static-verify bindings and obvious stubs.
5. Boot-verify application in an isolated environment.
6. Verify routes, pipeline contracts, dependencies, configuration, and permissions.
7. Traverse GUI controls with safe browser automation.
8. Intercept or sandbox side effects according to policy.
9. Classify every discovered manifestation exactly once.
10. Assert coverage, uniqueness, schema, and arithmetic invariants.
11. Emit a machine-readable ledger and preserve evidence.
12. Only after controlled successful execution may a capability become `EXECUTABLE_CONFIRMED`.

Steps 1-4 and 9-11 are represented by this PoC. Steps 5-8 and 12 remain separate higher-assurance phases.

## Identity and evidence safeguards

- Source taxonomy is not canonical capability identity.
- Names, normalized names, counts, nearest matches, same category, or source absence cannot establish identity.
- Regex/text search is discovery, not exhaustive semantic parsing.
- Raw labels are preserved separately from normalized labels.
- Each source manifestation receives a content-bound manifestation ID; that ID identifies the manifestation in the snapshot, not a cross-version canonical capability.
- Dynamic listeners, ancestor-form semantics, generated controls, and unresolved indirection fail closed to `UNRESOLVED` where detected and may remain outside a lexical discovery denominator where not detectable.
- No repository-wide completeness claim is made from the PoC denominator.

## PoC classifications

The static Spiderweb PoC emits exactly one of:

- `WIRED`: a local `onClick` binding is visible. Downstream executability is unproven.
- `DEAD_SURFACE`: an app-authored plain `<button>` manifestation has no local `onClick` and is not an explicit submit button.
- `STUB`: a same-file named handler resolves lexically and contains a narrow, explicit TODO/not-implemented marker.
- `UNRESOLVED`: the manifestation has semantics this lexical pass cannot safely adjudicate, such as an explicit submit button without local `onClick`.

These are source-manifestation states, not canonical feature identity states.

## Existing Spiderweb overlap

Spiderweb already has a detailed manual/live GUI audit and a Playwright runtime matrix. Those provide stronger runtime evidence for covered controls and remain authoritative for their stated snapshots. This PoC adds a deterministic machine-readable denominator and regression ledger; it must not overwrite stronger evidence with weaker lexical classifications.

The unfinished-implementation ledger is complementary: it tracks project implementation gaps at a broader capability level, while this auditor inventories GUI manifestations. Future canonical federation logic should ingest both as separate source manifestations and adjudicate conflicts explicitly.

## Required invariants

For the bounded discovered set:

- `discovered_manifestations == classified_manifestations`
- `sum(by_final_state.values()) == discovered_manifestations`
- manifestation IDs are unique
- every manifestation has one allowed final state
- no target feature is executed by the static phase

Any unexplained mismatch is `FAIL`.

A successful static run is `AUDIT_ONLY`, never executable certification.

## Rollout gate

Do not replicate this scanner blindly across the seven repositories. First validate this PoC against Spiderweb's existing live GUI audit and runtime matrix, measure false positives/false negatives, then move the generic policy/schema into `thehub-pr`. Per-repository adapters should be selected from inspected frameworks (React/JSX, Streamlit, Tkinter, Gradio, etc.) rather than assumed globally.
