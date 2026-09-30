import { vi, expect } from "vitest";

expect.extend({
  toBeTrue(received) {
    return { pass: received === true, message: () => `expected ${received} to be true` };
  },
  toBeFalse(received) {
    return { pass: received === false, message: () => `expected ${received} to be false` };
  },
});

function jasmineCompatSpy(spy) {
  const api = spy;
  api.and = {
    returnValue(value) { spy.mockReturnValue(value); return api; },
    resolveTo(value) { spy.mockResolvedValue(value); return api; },
    callFake(fn) { spy.mockImplementation(fn); return api; },
  };
  api.calls = {
    mostRecent() { return { args: spy.mock.calls.at(-1) ?? [] }; },
    count() { return spy.mock.calls.length; },
  };
  return api;
}

globalThis.spyOn = (target, key) => jasmineCompatSpy(vi.spyOn(target, key));
globalThis.jasmine = {
  createSpy(name) { return jasmineCompatSpy(vi.fn().mockName(name)); },
  any(ctor) { return expect.any(ctor); },
};

function stableMatchMedia(query) {
  return {
    matches: false,
    media: query,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() { return false; },
  };
}

if (typeof window !== "undefined") {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: stableMatchMedia,
  });
}
