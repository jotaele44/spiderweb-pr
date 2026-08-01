import { describe, it, expect, vi, afterEach } from "vitest";

import {
  REQUEST_TIMEOUT_MS,
  fetchWithTimeout,
  getPipelineStatus,
  startPipeline,
  streamPipeline,
} from "./client";

// These cover the failure paths that previously had no exit: a backend that
// accepts a connection but never answers, and a /pipeline/run that errors.
// Both used to leave the UI stuck — the first on "Loading PRIIS data…"
// forever, the second on a STOP button for a job that never started.

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const jsonResponse = (body: unknown, ok = true, status = 200) =>
  ({ ok, status, json: () => Promise.resolve(body) }) as unknown as Response;

describe("fetchWithTimeout", () => {
  it("rejects once the timeout elapses rather than hanging", async () => {
    vi.useFakeTimers();
    // A backend that never responds, but does honour the abort signal.
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_input: string, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () =>
              reject(new DOMException("aborted", "AbortError")),
            );
          }),
      ),
    );

    const pending = fetchWithTimeout("/never-answers", {}, 50);
    const assertion = expect(pending).rejects.toThrow(/timed out after 50ms/);
    await vi.advanceTimersByTimeAsync(51);
    await assertion;
  });

  it("passes a successful response straight through", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse({ ok: 1 }))));
    const res = await fetchWithTimeout("/fine");
    expect(res.ok).toBe(true);
  });

  it("uses a bounded default timeout", () => {
    expect(REQUEST_TIMEOUT_MS).toBeGreaterThan(0);
    expect(REQUEST_TIMEOUT_MS).toBeLessThanOrEqual(30_000);
  });
});

describe("startPipeline", () => {
  it("throws on a non-ok response instead of returning an undefined job_id", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse({ detail: "boom" }, false, 500))));
    await expect(startPipeline()).rejects.toThrow(/pipeline\/run → 500/);
  });

  it("throws when the body carries no job_id", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse({ status: "running" }))));
    await expect(startPipeline()).rejects.toThrow(/no job_id/);
  });

  it("returns the job on success", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse({ job_id: "j-1", status: "running" }))));
    await expect(startPipeline()).resolves.toEqual({ job_id: "j-1", status: "running" });
  });
});

describe("streamPipeline after a dropped stream", () => {
  // A stream error is not a dead job — the subprocess in pipeline_run keeps
  // going. Abandoning it here would strand a job the operator can no longer stop
  // or monitor, so the stream falls back to polling and keeps reporting running.
  class FakeEventSource {
    static last: FakeEventSource | null = null;
    onmessage: ((ev: MessageEvent<string>) => void) | null = null;
    onerror: (() => void) | null = null;
    closed = false;
    constructor(public url: string) {
      FakeEventSource.last = this;
    }
    // The 'done' event never fires in these cases; the drop is the scenario.
    addEventListener(): void { return undefined; }
    close() {
      this.closed = true;
    }
  }

  function useFakeEventSource() {
    FakeEventSource.last = null;
    vi.stubGlobal("EventSource", FakeEventSource);
  }

  it("keeps polling and does not report failure while the job is still running", async () => {
    vi.useFakeTimers();
    useFakeEventSource();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse({ job_id: "j-1", status: "running" }))),
    );
    const onDone = vi.fn();
    const onError = vi.fn();
    const onDegraded = vi.fn();

    const stream = streamPipeline("j-1", () => undefined, onDone, onError, onDegraded);
    FakeEventSource.last!.onerror!();

    await vi.advanceTimersByTimeAsync(6000);
    expect(onDegraded).toHaveBeenCalledOnce();
    expect(onError).not.toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();

    // close() must stop the polling loop, not just the socket.
    stream.close();
    const callsAfterClose = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.length;
    await vi.advanceTimersByTimeAsync(6000);
    expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBe(callsAfterClose);
  });

  it("resolves the run once polling sees a terminal state", async () => {
    vi.useFakeTimers();
    useFakeEventSource();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse({ job_id: "j-1", status: "done", returncode: 0 }))),
    );
    const onDone = vi.fn();
    const onError = vi.fn();

    streamPipeline("j-1", () => undefined, onDone, onError);
    FakeEventSource.last!.onerror!();
    await vi.advanceTimersByTimeAsync(100);

    expect(onDone).toHaveBeenCalledWith(0);
    expect(onError).not.toHaveBeenCalled();
  });

  it("reports failure only after the status endpoint stays unreachable", async () => {
    vi.useFakeTimers();
    useFakeEventSource();
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("connection refused"))));
    const onError = vi.fn();

    streamPipeline("j-1", () => undefined, vi.fn(), onError);
    FakeEventSource.last!.onerror!();
    await vi.advanceTimersByTimeAsync(30_000);

    expect(onError).toHaveBeenCalledOnce();
    expect(onError.mock.calls[0][0]).toMatch(/unreachable/);
  });
});

describe("getPipelineStatus", () => {
  it("reports the terminal state so a dropped stream can be resolved", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse({ job_id: "j-1", status: "done", returncode: 0 }))),
    );
    await expect(getPipelineStatus("j-1")).resolves.toMatchObject({ status: "done", returncode: 0 });
  });

  it("throws when the job is unknown to the backend", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse({ detail: "job not found" }, false, 404))));
    await expect(getPipelineStatus("gone")).rejects.toThrow(/404/);
  });
});
