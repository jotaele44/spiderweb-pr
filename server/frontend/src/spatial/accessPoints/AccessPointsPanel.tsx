import { AccessPointDetail } from "./AccessPointDetail";
import { REGISTRY_TITLES, shortHash, type DrawnStatusGroup } from "./accessPointsApi";
import type { NotDrawnReason } from "./accessPointLayers";
import { SourceCoveragePanel } from "./SourceCoveragePanel";
import type { AccessPointsControllerState, RegistryView } from "./useAccessPointsController";

const GROUP_LABEL: Record<DrawnStatusGroup, string> = {
  verified: "Verified",
  candidate: "Candidate",
  provisional: "Provisional",
};

const LEGEND: Record<DrawnStatusGroup, string> = {
  verified: "filled disc — independently reviewed, with a directly observed opening",
  candidate: "open ring — backed by a source, not adjudicated",
  provisional: "small faint ring — noticed, source not yet registered",
};

const REASON: Record<NotDrawnReason, string> = {
  "no-coordinates": "no registered coordinates",
  "non-point-geometry": "geometry is not a point",
  retired: "rejected or superseded",
};

/** Text for a registry's load state. "Loaded" is said only once the map has drawn it. */
export function registryStatusText(view: RegistryView): string {
  switch (view.state) {
    case "off":
      return "Off";
    case "loading":
      return "Loading records…";
    case "source-ready":
      return "Records received; drawing…";
    case "loaded":
      return `${view.drawnCount} drawn on the map`;
    case "error":
      return "Unavailable";
  }
}

function RegistryBlock({ view, controller }: { view: RegistryView; controller: AccessPointsControllerState }) {
  const title = REGISTRY_TITLES[view.registry];
  const unlocated = view.notDrawn.filter((record) => record.reason === "no-coordinates").length;
  return (
    <div className="ap-registry" data-registry={view.registry} data-load-state={view.state}>
      <button
        type="button"
        className="navbtn"
        aria-pressed={view.enabled}
        onClick={() => controller.toggleRegistry(view.registry)}
      >
        {title}
      </button>
      <span className="subtle" role="status">
        {registryStatusText(view)}
      </span>
      {view.state === "error" && (
        <p className="ap-alert" role="alert">
          {title} could not be loaded: {view.error}
        </p>
      )}
      {view.enabled && view.snapshot && (
        <>
          {view.snapshot.truncated && (
            <p className="ap-alert" role="alert">
              Only part of this registry was read. Counts below are incomplete.
            </p>
          )}
          {unlocated > 0 && (
            <p className="ap-note" role="note">
              {unlocated} {unlocated === 1 ? "record has" : "records have"} no registered coordinates and{" "}
              {unlocated === 1 ? "is" : "are"} not drawn.
            </p>
          )}
          {view.notDrawn.length > 0 && (
            <ul className="ap-list" aria-label={`${title} records not drawn on the map`}>
              {view.notDrawn.map(({ feature, reason }) => (
                <li key={feature.id}>
                  <button
                    type="button"
                    className="linklike mono"
                    onClick={() => controller.select({ registry: view.registry, featureId: feature.id })}
                  >
                    {feature.id}
                  </button>{" "}
                  <span className="subtle">
                    {[...feature.properties.provisional_labels, ...feature.properties.locality_labels].join(" · ")}
                    {" — "}
                    {REASON[reason]}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="subtle">
            {view.snapshot.provenance.path} · sha256 {shortHash(view.snapshot.provenance.sha256)}{" "}
            <button
              type="button"
              className="linklike"
              aria-pressed={controller.coverageRegistry === view.registry}
              onClick={() =>
                controller.setCoverageRegistry(controller.coverageRegistry === view.registry ? null : view.registry)
              }
            >
              Sources
            </button>
          </p>
        </>
      )}
    </div>
  );
}

/** Layer group for the two access-point registries, with their evidence views. */
export function AccessPointsPanel({ controller }: { controller: AccessPointsControllerState }) {
  const anyOn = controller.registries.some((view) => view.enabled);
  return (
    <div className="ap-panel">
      <h2>Access points</h2>
      <p className="subtle">
        Candidate records for review. A mapped anomaly is not an access point, an access point is not a passage, and
        a passage is not a connection.
      </p>
      {controller.registries.map((view) => (
        <RegistryBlock key={view.registry} view={view} controller={controller} />
      ))}
      {anyOn && (
        <>
          <div className="ap-filter" role="group" aria-label="Show records by status">
            {controller.statusGroups.map((group) => (
              <button
                key={group}
                type="button"
                className="navbtn"
                aria-pressed={controller.groups[group]}
                onClick={() => controller.toggleGroup(group)}
              >
                {GROUP_LABEL[group]}
              </button>
            ))}
          </div>
          <ul className="ap-legend" aria-label="Map symbols">
            {controller.statusGroups.map((group) => (
              <li key={group} data-status-group={group}>
                <span className="ap-swatch" data-status-group={group} aria-hidden="true" />
                <strong>{GROUP_LABEL[group]}</strong>: {LEGEND[group]}
              </li>
            ))}
            <li>
              <span className="ap-swatch" data-status-group="halo" aria-hidden="true" />
              <strong>Halo</strong>: stated horizontal uncertainty (approximate ground radius). No halo means the
              uncertainty is unknown, not zero.
            </li>
          </ul>
        </>
      )}
      {controller.coverageRegistry && (
        <SourceCoveragePanel registry={controller.coverageRegistry} state={controller.coverage} />
      )}
      {controller.selectedFeature && (
        <AccessPointDetail
          feature={controller.selectedFeature}
          evidence={controller.evidence}
          onClose={() => controller.select(null)}
        />
      )}
    </div>
  );
}
