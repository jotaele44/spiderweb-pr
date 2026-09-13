import { useState } from "react";
import { selectedApplicableRows, sourceUrl } from "./aoiRecommendations";
import type { DatasetRecommendations } from "./aoiRecommendations";

/** Presentation of backend decisions; choosing alternatives does not certify equivalence. */
export function AoiDatasetSelector({ response, selectedIds, onSelectionChange }: {
  response: DatasetRecommendations; selectedIds: string[]; onSelectionChange: (ids: string[]) => void;
}) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const recommended = response.datasets.filter((dataset) => dataset.recommended);
  const visible = recommended.filter((d) => `${d.label_raw} ${d.provider_id ?? ""} ${d.dataset_id}`.toLowerCase().includes(query.toLowerCase()));
  const other = response.datasets.filter((dataset) => !dataset.recommended);
  const rows = selectedApplicableRows(response, selectedIds);
  const pages = Math.max(1, Math.ceil(rows.length / 50)), current = Math.min(page, pages - 1);
  const choose = (id: string, checked: boolean) => {
    setPage(0); onSelectionChange(checked ? [...selectedIds, id] : selectedIds.filter((item) => item !== id));
  };
  return <section aria-label="Dataset comparison selection" data-testid="aoi-dataset-selector">
    <h3>Datasets applying to this AOI</h3>
    <p>{recommended.length} recommended / {response.counts.datasets_examined} examined. {response.unresolved_dataset_ids.length} have unresolved file-list evidence.</p>
    <p>Recommendations prove indexed footprint overlap, not valid-data coverage. Choose sources independently; none is preferred or automatically selected.</p>
    <details open>
      <summary>Select datasets for comparison ({selectedIds.length} selected)</summary>
      <label>Search applicable datasets <input value={query} onChange={(event) => setQuery(event.target.value)} /></label>
      <p>{visible.length} of {recommended.length} recommended options shown.</p>
      <fieldset><legend>Applicable datasets</legend>
        {visible.map((dataset) => <label key={dataset.dataset_id} style={{ display: "block", minHeight: 44, overflowWrap: "anywhere" }}>
          <input type="checkbox" checked={selectedIds.includes(dataset.dataset_id)} onChange={(event) => choose(dataset.dataset_id, event.target.checked)} />
          {dataset.label_raw} · {dataset.provider_id ?? "provider unresolved"} · {dataset.counts.applicable_files} matching files
          <small style={{ display: "block" }}>{dataset.dataset_id} · snapshot {dataset.catalog_sha256?.slice(0, 12) ?? "unbound"}</small>
          {dataset.file_resolution_state !== "PASS" && <strong> Incomplete file list: {dataset.counts.unresolved} unresolved rows.</strong>}
        </label>)}
        {!recommended.length && <p role="status">No verified applicable options in the examined catalogs. Unresolved catalogs are not evidence of absence.</p>}
      </fieldset>
      <button type="button" disabled={!selectedIds.length} onClick={() => { setPage(0); onSelectionChange([]); }}>Clear comparison selection</button>
    </details>
    <details><summary>Other dataset decisions ({other.length})</summary>
      {other.map((d) => <p key={d.dataset_id}>{d.label_raw} · {d.recommendation_state} · {d.counts.examined} rows examined · {d.reasons.join("; ") || "No blocking evidence in this snapshot"}</p>)}
    </details>
    <p>{selectedIds.length} datasets selected · {rows.length} corresponding source files · known bytes {rows.reduce((sum, row) => sum + (row.size_bytes ?? 0), 0).toLocaleString()} · {rows.filter((row) => row.size_bytes === null).length} unknown sizes.</p>
    <div style={{ overflowX: "auto", maxHeight: "30dvh" }} tabIndex={0} aria-label="Files corresponding to selected datasets">
      <table><caption>Selected AOI files, page {current + 1} of {pages}. Full source records remain in the exported response.</caption>
        <thead><tr><th>Dataset</th><th>Exact asset / row</th><th>AOI relation</th><th>Source file</th><th>Validation</th></tr></thead>
        <tbody>{rows.slice(current * 50, (current + 1) * 50).map((row) => <tr key={row.row_id}>
          <td>{row.dataset_id}</td><td>{row.asset_id}<br />{row.row_id}</td><td>{row.relation}</td>
          <td>{sourceUrl(row) ? <a href={sourceUrl(row)!} target="_blank" rel="noopener noreferrer">Source file URL (external)</a> : "URL unresolved"}</td>
          <td>{row.validation_state}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <button type="button" disabled={current === 0} onClick={() => setPage(current - 1)}>Previous selected files</button>
    <button type="button" disabled={current + 1 >= pages} onClick={() => setPage(current + 1)}>Next selected files</button>
    <p>Acquisition remains disabled. Global source inventory completeness and source equivalence remain unresolved.</p>
  </section>;
}
