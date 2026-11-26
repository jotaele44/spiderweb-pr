# D16 — Persistent execution durability receipt

| | |
|---|---|
| Subject | `spiderweb/geo_sar/jobs.py`, `spiderweb/geo_sar/handlers.py`, `scripts/geo_sar_worker.py` |
| Suite | `tests/test_geo_sar_job_durability.py` |
| Run | 2026-11-26, Linux, Python 3.13, four consecutive runs |
| Result | **12 passed, 0 failed** in each run (about 22 s) |
| Base | spiderweb-pr `00ce0f9e8fec2a5c764881bf71ec00915583eb60` plus this change |

## Verdict

| | |
|---|---|
| Ten mandatory durability tests | **PASS**, for local steps |
| AFK continuity certification | **WITHHELD** |

The ten tests pass. Certification is withheld because the tests do not cover
what an unattended acquisition actually depends on; see "Not covered".

## How the tests work

Workers are separate operating-system processes started in their own session.
An interruption is `SIGKILL` sent to the worker while it is copying. Nothing
simulates a restart by calling a function. The step under test copies a file
on local disk in 60 chunks with a checkpoint after each; no test uses the
network.

## Results

| # | Mandatory test | Result | What is asserted |
|---|---|---|---|
| 01 | Survives conversation termination | PASS | The process that submits the job exits; the job stays queued; a worker started afterwards completes it and the artifact hash is correct |
| 02 | Survives frontend disconnection | PASS | A client following the job's events is killed mid-run; the same worker finishes; exactly one claim was made |
| 03 | Survives worker interruption | PASS | Worker killed mid-copy; the lease expires; a second worker completes the step and the step that depends on it; hash correct; no partial file left |
| 04 | Checkpoints survive restart | PASS | A fresh process reads the checkpoint the killed worker wrote last; the bytes on disk up to that offset hash to the recorded value |
| 05 | Recovery does not duplicate mutations | PASS | One recorded effect and one file after recovery; a second job for the same bytes writes nothing; resubmission returns the same job; a changed resubmission is refused; an interrupted step not declared resumable stops for a decision and is claimed once only |
| 06 | Authorisation boundaries remain enforced | PASS | No grant, wrong level and too few bytes are each blocked before any handler runs, including after a worker is killed and replaced; an unnamed grant is rejected; a worker whose lease was taken over cannot complete, checkpoint, record an effect or fail the step |
| 07 | Evidence history remains intact | PASS | History before the kill is a prefix of history after recovery; every checkpoint, including superseded ones, is still readable; `UPDATE` and `DELETE` on the event table are rejected by the database |
| 08 | Resume starts from latest verified checkpoint | PASS | The second worker starts at exactly the last checkpoint offset and writes only the remainder; when the partial file is damaged first, the checkpoint is rejected, the copy restarts at zero and the result is still correct |
| 09 | Terminal failures are accurately reported | PASS | A failing step is tried three times, then marked failed with the provider's message; its dependants are blocked with the reason; an integrity failure is not retried and leaves no artifact; an unknown step kind fails with a named cause |
| 10 | Later session reconnects to original job | PASS | A new process finds the job by its idempotency key and reads only the events after its cursor |

Two further cases pass: dependency cycles and unknown dependencies are
refused at submit; a step awaiting a decision cannot be released without a
named person and a reason.

## Not covered

| Not covered | Consequence |
|---|---|
| Retrieval from a provider | The only mutating handler copies a local file. Interrupted network transfer, a provider that ignores range requests, a file that changes between attempts: untested. |
| Machine reboot or power loss | Durability of committed writes rests on SQLite's write-ahead log with full synchronisation. It was not tested by cutting power or rebooting. |
| Worker supervision | Nothing restarts a dead worker. Tests start the second worker themselves. Unattended running needs a process manager; none is configured. |
| A stalled worker that is still alive | A worker that hangs without dying keeps its lease only until it expires, and fencing then rejects its writes (test 06 covers the fencing). A handler that makes an outside change after losing its lease is not prevented from doing so. |
| Disk full, corrupted ledger file | Untested. |
| Several workers under load | Two workers at a time were used. Throughput and contention were not measured. |
| Resource admission | The ledger checks the byte ceiling of the grant. It does not check free disk, memory or concurrent transfers. |
| Platforms other than Linux | The suite is skipped where POSIX signals are absent. |
| Federation governance | The ledger is local to this repository. No thehub-pr admission, receipt or LOCKSTEP record is produced. |

## Known design limits

- A step that is mutating and not declared resumable stops in
  `NEEDS_RECONCILIATION` after an interruption and waits for a person. That is
  deliberate. It also means such a step cannot run unattended.
- Declaring a step resumable is a promise by its author that continuing from a
  checkpoint cannot repeat an outside change. The ledger cannot check the
  promise.
- The grant is stored with the job. Anyone who can write the ledger file can
  alter it.

## To lift the withholding

1. A provider retrieval handler, with tests 03, 04, 05 and 08 repeated against
   a local HTTP server that drops connections and against one real file.
2. A supervised worker, and a test that kills it and observes the restart.
3. A reboot test on a real machine.
4. A free-disk check before a step is claimed.
