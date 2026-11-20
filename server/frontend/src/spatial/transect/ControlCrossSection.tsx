import { useState } from "react";
import { errorMessage } from "../accessPoints/accessPointsApi";
import { fetchControlCrossSection, type CrossSection } from "./transectApi";
import { TransectProfile } from "./TransectProfile";

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; section: CrossSection }
  | { status: "error"; message: string };

/**
 * Shows the cross-section view on control data. No measured surface is
 * registered yet, so this is the only section the workbench can draw, and it
 * is labelled as synthetic wherever it appears.
 */
export function ControlCrossSection() {
  const [state, setState] = useState<State>({ status: "idle" });
  const load = () => {
    setState({ status: "loading" });
    fetchControlCrossSection()
      .then((section) => setState({ status: "ready", section }))
      .catch((reason: unknown) => setState({ status: "error", message: errorMessage(reason) }));
  };
  return (
    <div className="ap-cross-section">
      <h2>Land-to-sea cross-section</h2>
      <p className="subtle">
        No measured terrain or bathymetry surface is registered yet. The view can be exercised on synthetic control
        surfaces, which are not evidence about any real place.
      </p>
      {state.status !== "ready" && (
        <button type="button" className="act" onClick={load} disabled={state.status === "loading"}>
          Show control cross-section
        </button>
      )}
      {state.status === "loading" && <p role="status">Loading cross-section…</p>}
      {state.status === "error" && (
        <p className="ap-alert" role="alert">
          Cross-section could not be loaded: {state.message}
        </p>
      )}
      {state.status === "ready" && <TransectProfile section={state.section} />}
    </div>
  );
}
