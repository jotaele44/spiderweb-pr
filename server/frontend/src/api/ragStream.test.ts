import { afterEach, describe, expect, it, vi } from "vitest";

import { streamRagQuery } from "./client";

function response(body: string): Response {
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("streamRagQuery", () => {
  it("preserves tokens and the explicit terminal return code", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(response("data: evidence line\n\nevent: done\ndata: {\"returncode\":7}\n\n"))),
    );

    const tokens: string[] = [];
    const rc = await new Promise<number>((resolve, reject) => {
      streamRagQuery("test", (token) => tokens.push(token), resolve, (message) => reject(new Error(message)));
    });

    expect(tokens).toEqual(["evidence line"]);
    expect(rc).toBe(7);
  });

  it("fails closed when the stream ends without a terminal event", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(response("data: partial answer\n\n"))));
    const done = vi.fn();

    const error = await new Promise<string>((resolve) => {
      streamRagQuery("test", () => undefined, done, resolve);
    });

    expect(error).toMatch(/ended before a terminal completion event/);
    expect(done).not.toHaveBeenCalled();
  });

  it("fails closed on a malformed terminal event", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(response("event: done\ndata: not-json\n\n"))));
    const done = vi.fn();

    const error = await new Promise<string>((resolve) => {
      streamRagQuery("test", () => undefined, done, resolve);
    });

    expect(error).toMatch(/malformed completion event/);
    expect(done).not.toHaveBeenCalled();
  });
});
