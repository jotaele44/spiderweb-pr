import { describe, it, expect, vi, afterEach } from "vitest";

import {
  REQUEST_TIMEOUT_MS,
  fetchWithTimeout,
  getPipelineStatus,
  startPipeline,
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
