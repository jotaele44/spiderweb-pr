import { fireEvent, render, waitFor } from "@testing-library/react";
import { SpatialDatasetIntake } from "./SpatialDatasetIntake";

describe("SpatialDatasetIntake", () => {
  it("renders one canonical manifest-first intake surface", () => {
    const view=render(<SpatialDatasetIntake/>);
    expect(view.getByText("Dataset intake & preflight")).toBeTruthy();
    expect(view.getByLabelText("File upload")).toBeTruthy();
  });

  it("ingests GeoJSON through the manifest and exposes explicit role assignment", async () => {
    const view=render(<SpatialDatasetIntake/>);
    const file=new File([JSON.stringify({type:"FeatureCollection",features:[{type:"Feature",id:"A",properties:{},geometry:{type:"Point",coordinates:[-66.1,18.4]}}]})],"a.geojson",{type:"application/geo+json"});
    fireEvent.change(view.getByLabelText("File upload"),{target:{files:[file]}});
    await waitFor(()=>expect(view.getByText(/1 uploaded/)).toBeTruthy());
    expect(view.getByText(/geojson · EPSG:4326/)).toBeTruthy();
    expect(view.getByLabelText(/Role for runtime:/)).toBeTruthy();
    expect(view.getByLabelText("Analysis preset")).toBeTruthy();
  });

  it("shows GeoPackage as blocked instead of fabricating parser support", async () => {
    const view=render(<SpatialDatasetIntake/>);
    const file=new File(["not-a-real-gpkg"],"authority.gpkg",{type:"application/geopackage+sqlite3"});
    fireEvent.change(view.getByLabelText("File upload"),{target:{files:[file]}});
    await waitFor(()=>expect(view.getByText(/GeoPackage adapter is BLOCKED/)).toBeTruthy());
  });
});