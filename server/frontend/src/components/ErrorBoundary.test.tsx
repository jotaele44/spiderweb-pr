import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { ErrorBoundary } from "./ErrorBoundary";

function Boom(): never {
  throw new Error("module exploded");
}

describe("ErrorBoundary", () => {
  // React logs caught render errors to console.error; silence it so a passing
  // run isn't full of expected stack traces.
  beforeEach(() => vi.spyOn(console, "error").mockImplementation(() => undefined));
  afterEach(() => vi.restoreAllMocks());

  it("renders children when nothing throws", () => {
    render(
      <ErrorBoundary>
        <p>all good</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("all good")).toBeTruthy();
  });

  it("renders a fallback instead of unmounting the tree when a child throws", () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("module exploded")).toBeTruthy();
    expect(screen.getByRole("button", { name: "RETRY" })).toBeTruthy();
  });

  it("offers a reload, not a soft reset, when the fallback replaces the whole app", () => {
    // A soft reset re-renders the same children, so a deterministic throw lands
    // straight back on the fallback. At the root that leaves the user with a
    // button that cannot recover, so the root boundary reloads instead.
    render(
      <ErrorBoundary recoverBy="reload">
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("button", { name: "RELOAD" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "RETRY" })).toBeNull();
  });

  it("passes the error and a reset callback to a custom fallback", () => {
    render(
      <ErrorBoundary fallback={(error) => <p>caught: {error.message}</p>}>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText("caught: module exploded")).toBeTruthy();
  });
});
