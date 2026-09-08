# Diagnostic job lifecycle

The FastAPI diagnostic service owns pipeline and RAG child processes through
`server/backend/jobs.py`. A capture thread starts with each child, so its output
pipe drains even when no browser is connected. Each viewer replays its own cursor
over the captured output; viewers do not consume one another's messages.

## Limits and results

The process-local registry permits four running jobs and retains up to 32 jobs.
Each job captures at most 16 MiB of merged stdout/stderr in a temporary file.
When retention fills, the oldest completed job without active viewers is evicted.
If no slot is available, launch endpoints return HTTP 429 before starting a child
or sending SSE headers. These limits can be configured when constructing the
registry; invalid limits are rejected.

Exceeding the output limit stops the child and reports `output_limit_exceeded`.
Capture/storage failures also fail the job. `returncode` represents the effective
job outcome; when capture failure or cancellation overrides a zero child exit,
`process_returncode` preserves the child's actual exit code. Output loss is never
represented as successful capture.

Captured bytes remain unchanged. SSE renders UTF-8 with replacement for invalid
bytes, preserves spaces, and splits very long lines into bounded chunks. This
display conversion does not alter the retained raw bytes.

## Viewing and cancellation

- `GET /pipeline/jobs` lists retained IDs, status, and captured byte counts. Use it
  to find a job when the launch response was lost.
- `GET /pipeline/status/{job_id}` remains usable after cancellation or completion.
- `GET /pipeline/events/{job_id}` replays retained output and follows a running job.
  SSE IDs are byte offsets. Reconnecting with `Last-Event-ID` resumes at that
  offset; malformed or out-of-range cursors return HTTP 400.
- `DELETE /pipeline/{job_id}` waits for termination, escalates if needed, and keeps
  the terminal result for replay. Repeating it for a completed job is safe. If
  termination has not finished, the response is HTTP 503 rather than a false
  success. Missing/evicted IDs return HTTP 404.

Closing a pipeline viewer does not cancel the pipeline. A RAG query owns its
streaming job and cleans it up when the stream closes. Orderly application
shutdown stops and reaps owned children before closing their captured output.
On POSIX, registry children own separate sessions and cancellation signals the
whole process group, including descendants holding stdout open. Windows currently
terminates the direct child; descendant cleanup there is not certified.

## Lifetime boundary

This is a diagnostic execution registry, not a durable queue. IDs and captured
output are retained for the server process lifetime and are released by eviction
or shutdown. Hard process crashes, cross-worker coordination, and automatic
restart/replay of mutating jobs are outside this implementation. Run one server
worker for this registry. No interrupted job is automatically rerun.

Tests in `tests/test_backend_jobs.py` use real temporary children to exercise
no-viewer completion, independent live/late viewers, resume cursors, limits,
capture failure, cancellation, process cleanup, and HTTP failure boundaries.
