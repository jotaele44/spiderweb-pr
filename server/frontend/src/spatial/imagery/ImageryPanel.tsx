import {
  formatAcquired,
  formatBytes,
  type EriCatalog,
  type EriDataset,
  type EriFootprint,
} from "./eriApi";
import type { ImageryStatus } from "./useEriImagery";

export type CatalogState =
  | { status: "loading" }
  | { status: "ready"; catalog: EriCatalog }
  | { status: "error"; message: string };

export interface ImageryPanelProps {
  catalogState: CatalogState;
  onRetryCatalog: () => void;
  datasetId: string | null;
  onDataset: (id: string | null) => void;
  opacity: number;
  onOpacity: (opacity: number) => void;
  showFootprints: boolean;
  onShowFootprints: (show: boolean) => void;
  compareId: string | null;
  onCompare: (id: string | null) => void;
  basemapVisible: boolean;
  onBasemapVisible: (visible: boolean) => void;
  imageryStatus: ImageryStatus;
  footprintStatus: ImageryStatus;
  /** Current map zoom, or null before the map is ready. */
  zoom: number | null;
  onZoomToImagery: () => void;
  identified: EriFootprint | null;
  onClearIdentified: () => void;
  onCopyLink: () => void;
  linkCopied: boolean;
}

function groupByEvent(datasets: EriDataset[]): [string, EriDataset[]][] {
  const groups = new Map<string, EriDataset[]>();
  datasets.forEach((dataset) => {
    const label = dataset.event.replace(/_/g, " ");
    groups.set(label, [...(groups.get(label) ?? []), dataset]);
  });
  return [...groups.entries()];
}

function DatasetOptions({ datasets, exclude }: { datasets: EriDataset[]; exclude?: string | null }) {
  return (
    <>
      {groupByEvent(datasets).map(([event, members]) => (
        <optgroup key={event} label={event}>
          {members
            .filter((dataset) => dataset.id !== exclude)
            .map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.label}
              </option>
            ))}
        </optgroup>
      ))}
    </>
  );
}

export function imageryStatusText(status: ImageryStatus, belowMinZoom: boolean): string {
  if (status === "off") return "off";
  if (status === "error") return "error";
  if (belowMinZoom) return "zoom in";
  return status === "loading" ? "loading…" : "rendered";
}

/** Controls for the NOAA Emergency Response Imagery layer. */
export function ImageryPanel(props: ImageryPanelProps) {
  const { catalogState, datasetId, compareId, zoom } = props;
  const datasets = catalogState.status === "ready" ? catalogState.catalog.datasets : [];
  const dataset = datasets.find((entry) => entry.id === datasetId) ?? null;
  const belowMinZoom = dataset !== null && zoom !== null && zoom < dataset.min_zoom;

  return (
    <section className="imagery-panel" aria-labelledby="imagery-panel-title">
      <h2 id="imagery-panel-title">Aerial imagery</h2>
      <button
        className="navbtn"
        data-active={props.basemapVisible}
        aria-pressed={props.basemapVisible}
        onClick={() => props.onBasemapVisible(!props.basemapVisible)}
      >
        <span>Base map</span>
        <span>{props.basemapVisible ? "on" : "off"}</span>
      </button>

      {catalogState.status === "loading" && <p className="subtle">Loading imagery catalog…</p>}
      {catalogState.status === "error" && (
        <div className="imagery-inline-error" role="alert">
          <span>Imagery catalog unavailable — {catalogState.message}</span>
          {/* Not a bare "retry": the density overlay already has one in this panel. */}
          <button className="linklike" onClick={props.onRetryCatalog}>retry imagery catalog</button>
        </div>
      )}

      {catalogState.status === "ready" && (
        <>
          <label className="imagery-field">
            <span>NOAA emergency response flight</span>
            <select
              value={datasetId ?? ""}
              onChange={(event) => props.onDataset(event.target.value || null)}
            >
              <option value="">Off</option>
              <DatasetOptions datasets={datasets} />
            </select>
          </label>

          {dataset && (
            <>
              <div className="imagery-meta">
                <span>{dataset.kind === "pre_event" ? "Pre-event baseline" : "Post-event"}</span>
                <span>{formatAcquired(dataset.acquired)}</span>
                <span data-status={props.imageryStatus}>
                  {imageryStatusText(props.imageryStatus, belowMinZoom)}
                </span>
              </div>
              {props.imageryStatus === "error" && (
                <div className="imagery-inline-error" role="alert">
                  <span>Imagery tiles unavailable — backend offline or NOAA bucket unreachable.</span>
                </div>
              )}
              {belowMinZoom && (
                <div className="imagery-hint" role="status">
                  <span>
                    Imagery loads from zoom {dataset.min_zoom}. Outlines show where this flight has coverage.
                  </span>
                  <button className="linklike" onClick={props.onZoomToImagery}>zoom to imagery</button>
                </div>
              )}

              <label className="imagery-field">
                <span>Opacity · {Math.round(props.opacity * 100)}%</span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={Math.round(props.opacity * 100)}
                  onChange={(event) => props.onOpacity(Number(event.target.value) / 100)}
                />
              </label>

              <button
                className="navbtn"
                data-active={props.showFootprints}
                data-status={props.showFootprints ? props.footprintStatus : undefined}
                aria-pressed={props.showFootprints}
                onClick={() => props.onShowFootprints(!props.showFootprints)}
                title="Outline each image; click an outline to identify it"
              >
                <span>Image footprints</span>
                <span>
                  {props.showFootprints ? imageryStatusText(props.footprintStatus, false) : "off"}
                </span>
              </button>

              <label className="imagery-field">
                <span>Swipe compare with</span>
                <select
                  value={compareId ?? ""}
                  onChange={(event) => props.onCompare(event.target.value || null)}
                >
                  <option value="">Off</option>
                  <DatasetOptions datasets={datasets} exclude={dataset.id} />
                </select>
              </label>

              {props.identified && (
                <div className="imagery-identify" role="status" aria-label="Identified image">
                  <div className="imagery-identify-head">
                    <strong>Identified image</strong>
                    <button className="linklike" onClick={props.onClearIdentified}>clear</button>
                  </div>
                  <code>{props.identified.name}</code>
                  <span>
                    {props.identified.dataset_label} · {formatAcquired(props.identified.acquired)} ·{" "}
                    {formatBytes(props.identified.size_bytes)}
                  </span>
                  <a href={props.identified.url} target="_blank" rel="noreferrer">
                    Source GeoTIFF
                  </a>
                </div>
              )}

              <a className="imagery-source" href={dataset.source_url} target="_blank" rel="noreferrer">
                Browse this flight in the NOAA bucket
              </a>
            </>
          )}
        </>
      )}

      <button className="navbtn" onClick={props.onCopyLink} title="Copy a link to this exact map view">
        <span>Copy link to this view</span>
        <span>{props.linkCopied ? "copied" : ""}</span>
      </button>
    </section>
  );
}
