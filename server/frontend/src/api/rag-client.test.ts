import { afterEach, describe, expect, it, vi } from "vitest";

import { streamRagQuery } from "./client";

function responseWithSse(body: string): Response {
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

function runStream(body: string): Promise<{ tokens: string[]; errors: string[] }> {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(responseWithSse(body))));

  return new Promise((resolve) => {
    const tokens: string[] = [];
    const errors: string[] = [];
    streamRagQuery(
      "test query",
      (token) => tokens.push(token),
      () => resolve({ tokens, errors }),
      (message) => errors.push(message),
    );
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("streamRagQuery terminal semantics", () => {
  it("delivers output only when the backend terminates successfully", async () => {
    const result = await runStream(
      'data: grounded answer\n\nevent: done\ndata: {"returncode":0}\n\n',
    );

    expect(result.tokens).toEqual(["grounded answer"]);
    expect(result.errors).toEqual([]);
  });

  it("surfaces a non-zero backend return code instead of reporting blank success", async () => {
    const result = await runStream(
      'event: done\ndata: {"returncode":2}\n\n',
    );

    expect(result.tokens).toEqual([]);
    expect(result.errors).toEqual(["RAG backend exited with code 2"]);
  });

  it("rejects returncode zero when the backend produced no output", async () => {
    const result = await runStream(
      'event: done\ndata: {"returncode":0}\n\n',
    );

    expect(result.tokens).toEqual([]);
    expect(result.errors).toEqual(["RAG backend completed without producing output"]);
  });

  it("rejects a stream that closes without a terminal event", async () => {
    const result = await runStream("data: partial answer\n\n");

    expect(result.tokens).toEqual(["partial answer"]);
    expect(result.errors).toEqual(["RAG response stream ended without terminal status"]);
  });
});
