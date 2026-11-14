import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { EriDataset } from "./eriApi";
import { CoordinateReadout, formatCoordinate } from "./CoordinateReadout";
import { ImageryPanel, imageryStatusText, type ImageryPanelProps } from "./ImageryPanel";

const pre: EriDataset = {
  id: "pre_event_2022_cb2201a",
  label: "2022 Pre-Event — Puerto Rico & USVI",
  event: "2022_Pre_Event",
  flight: "CB2201a_OB_N_RGB",
  kind: "pre_event",
  acquired: "2022",
  bbox: [-67.3, 17.66, -64.55, 18.53],
  min_zoom: 14,
  max_zoom: 20,
  source_url: "https://noaa-eri-pds.s3.amazonaws.com/index.html#2022_Pre_Event/CB2201a_OB_N_RGB/",
};
const maria: EriDataset = {
  ...pre,
  id: "maria_20170924b",
  label: "Hurricane Maria — 24 Sep 2017 (b)",
  event: "2017_Hurricane_Maria",
  flight: "20170924b_RGB",
  kind: "post_event",
  acquired: "2017-09-24",
};

function props(overrides: Partial<ImageryPanelProps> = {}): ImageryPanelProps {
  return {
    catalogState: {
      status: "ready",
      catalog: { attribution: "NOAA", tile_size: 256, datasets: [pre, maria] },
    },
    onRetryCatalog: vi.fn(),
    datasetId: null,
    onDataset: vi.fn(),
    opacity: 1,
    onOpacity: vi.fn(),
    showFootprints: true,
    onShowFootprints: vi.fn(),
    compareId: null,
    onCompare: vi.fn(),
    basemapVisible: true,
    onBasemapVisible: vi.fn(),
    imageryStatus: "off",
    footprintStatus: "off",
    zoom: 16,
    onZoomToImagery: vi.fn(),
    identified: null,
    onClearIdentified: vi.fn(),
    onCopyLink: vi.fn(),
    linkCopied: false,
    ...overrides,
  };
}

describe("ImageryPanel", () => {
  it("offers every flight grouped by event, and nothing else until one is chosen", () => {
    const p = props();
    render(<ImageryPanel {...p} />);
    const select = screen.getByLabelText("NOAA emergency response flight");
    expect(screen.getByRole("group", { name: "2022 Pre Event" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "2017 Hurricane Maria" })).toBeTruthy();
    expect(screen.queryByLabelText(/Opacity/)).toBeNull();
    fireEvent.change(select, { target: { value: maria.id } });
    expect(p.onDataset).toHaveBeenCalledWith(maria.id);
    fireEvent.change(select, { target: { value: "" } });
    expect(p.onDataset).toHaveBeenLastCalledWith(null);
  });

  it("exposes opacity, footprints and compare for the selected flight", () => {
    const p = props({ datasetId: pre.id, imageryStatus: "loaded", footprintStatus: "loaded", opacity: 0.6 });
    render(<ImageryPanel {...p} />);
    expect(screen.getByText("Pre-event baseline")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Opacity · 60%"), { target: { value: "35" } });
    expect(p.onOpacity).toHaveBeenCalledWith(0.35);
    fireEvent.click(screen.getByRole("button", { name: /Image footprints/ }));
    expect(p.onShowFootprints).toHaveBeenCalledWith(false);
    const compare = screen.getByLabelText("Swipe compare with");
    // The selected flight cannot be compared with itself.
    expect([...compare.querySelectorAll("option")].map((option) => option.value)).toEqual(["", maria.id]);
    fireEvent.change(compare, { target: { value: maria.id } });
    expect(p.onCompare).toHaveBeenCalledWith(maria.id);
    expect(screen.getByRole("link", { name: /NOAA bucket/ }).getAttribute("href")).toBe(pre.source_url);
  });

  it("explains the minimum zoom and offers to go there", () => {
    const p = props({ datasetId: pre.id, imageryStatus: "loaded", zoom: 9 });
    render(<ImageryPanel {...p} />);
    expect(screen.getByText(/Imagery loads from zoom 14/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "zoom to imagery" }));
    expect(p.onZoomToImagery).toHaveBeenCalled();
  });

  it("shows the identified image with its source link", () => {
    const p = props({
      datasetId: pre.id,
      identified: {
        name: "CB2201a_OB_NC0660730w182830n.tif",
        dataset_id: pre.id,
        dataset_label: pre.label,
        acquired: "2022",
        size_bytes: 65_400_000,
        url: "https://noaa-eri-pds.s3.amazonaws.com/2022_Pre_Event/CB2201a_OB_N_RGB/CB2201a_OB_NC0660730w182830n.tif",
      },
    });
    render(<ImageryPanel {...p} />);
    expect(screen.getByText("CB2201a_OB_NC0660730w182830n.tif")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Source GeoTIFF" }).getAttribute("href")).toContain("C0660730w182830n.tif");
    fireEvent.click(screen.getByRole("button", { name: "clear" }));
    expect(p.onClearIdentified).toHaveBeenCalled();
  });

  it("reports a catalog failure with a retry, and a tile failure", () => {
    const p = props({ catalogState: { status: "error", message: "request failed (503)" } });
    const { unmount } = render(<ImageryPanel {...p} />);
    expect(screen.getByRole("alert").textContent).toContain("503");
    fireEvent.click(screen.getByRole("button", { name: "retry imagery catalog" }));
    expect(p.onRetryCatalog).toHaveBeenCalled();
    unmount();
    render(<ImageryPanel {...props({ datasetId: pre.id, imageryStatus: "error" })} />);
    expect(screen.getByRole("alert").textContent).toContain("Imagery tiles unavailable");
  });

  it("toggles the base map and copies the link", () => {
    const p = props({ linkCopied: true });
    render(<ImageryPanel {...p} />);
    fireEvent.click(screen.getByRole("button", { name: /Base map/ }));
    expect(p.onBasemapVisible).toHaveBeenCalledWith(false);
    const copy = screen.getByRole("button", { name: /Copy link to this view/ });
    expect(copy.textContent).toContain("copied");
    fireEvent.click(copy);
    expect(p.onCopyLink).toHaveBeenCalled();
  });

  it("words the status", () => {
    expect(imageryStatusText("off", false)).toBe("off");
    expect(imageryStatusText("loaded", true)).toBe("zoom in");
    expect(imageryStatusText("loading", false)).toBe("loading…");
    expect(imageryStatusText("loaded", false)).toBe("rendered");
    expect(imageryStatusText("error", true)).toBe("error");
  });
});

describe("CoordinateReadout", () => {
  it("formats hemispheres", () => {
    expect(formatCoordinate(18.4655, -66.1167)).toBe("18.46550°N 66.11670°W");
    expect(formatCoordinate(-1.5, 2.25)).toBe("1.50000°S 2.25000°E");
  });

  it("follows the cursor and zoom of the map", () => {
    const handlers: Record<string, (event?: unknown) => void> = {};
    let zoom = 8.4;
    const map = {
      on: (name: string, handler: (event?: unknown) => void) => void (handlers[name] = handler),
      off: vi.fn(),
      getZoom: () => zoom,
    };
    const mapRef = { current: map } as never;
    render(<CoordinateReadout mapRef={mapRef} ready />);
    expect(screen.getByTestId("map-readout").textContent).toBe("—z 8.4");
    fireEvent.click(document.body); // flush
    zoom = 15.25;
    handlers.zoom();
    handlers.mousemove({ lngLat: { lat: 18.4655, lng: -66.1167 } });
    return screen.findByText("18.46550°N 66.11670°W").then(() => {
      expect(screen.getByTestId("map-readout").textContent).toContain("z 15.3");
    });
  });
});
