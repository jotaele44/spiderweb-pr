import { describe, expect, it } from "vitest";
import { formatViewHash, parseViewHash } from "./viewHash";

describe("map view fragment", () => {
  it("round-trips a full state", () => {
    const hash = formatViewHash({
      view: { zoom: 16, lat: 18.4655, lng: -66.1167 },
      imagery: "pre_event_2022_cb2201a",
      opacity: 0.6,
      compare: "maria_20170924b",
      footprints: false,
      basemap: false,
    });
    expect(hash).toBe(
      "#map=16.00/18.46550/-66.11670&eri=pre_event_2022_cb2201a&op=0.6&cmp=maria_20170924b&fp=0&base=0",
    );
    expect(parseViewHash(hash)).toEqual({
      view: { zoom: 16, lat: 18.4655, lng: -66.1167 },
      imagery: "pre_event_2022_cb2201a",
      opacity: 0.6,
      compare: "maria_20170924b",
      footprints: false,
      basemap: false,
    });
  });

  it("omits defaults and imagery-only options when no flight is selected", () => {
    expect(
      formatViewHash({ view: { zoom: 8.4, lat: 18.22, lng: -66.35 }, opacity: 0.5, compare: "x", footprints: false, basemap: true }),
    ).toBe("#map=8.40/18.22000/-66.35000");
    expect(formatViewHash({})).toBe("");
  });

  it("preserves fragment keys it does not own", () => {
    expect(formatViewHash({ imagery: "a_b" }, "#panel=graph&eri=old")).toBe("#eri=a_b&panel=graph");
  });

  it("ignores malformed values", () => {
    expect(parseViewHash("#map=abc/1/2&eri=../etc&op=nope&fp=7&base=yes&cmp=A%20B")).toEqual({});
    expect(parseViewHash("#map=12/95/-66")).toEqual({});
    expect(parseViewHash("")).toEqual({});
  });

  it("clamps opacity and zoom", () => {
    expect(parseViewHash("#map=40/18/-66&op=3")).toEqual({ view: { zoom: 24, lat: 18, lng: -66 }, opacity: 1 });
  });
});
