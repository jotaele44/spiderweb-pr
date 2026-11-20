import { REGISTRY_TITLES, shortHash, words, type AccessPointRegistryId } from "./accessPointsApi";
import type { CoverageState } from "./useAccessPointsController";

/** Sources a registry holds, grouped by provider. A source is a reference, not a measurement. */
export function SourceCoveragePanel({ registry, state }: { registry: AccessPointRegistryId; state: CoverageState }) {
  return (
    <section className="card ap-coverage" aria-label={`${REGISTRY_TITLES[registry]} sources`}>
      <h3>{REGISTRY_TITLES[registry]} — sources</h3>
      {state.status === "loading" && <p role="status">Loading sources…</p>}
      {state.status === "error" && (
        <p className="ap-alert" role="alert">
          Sources could not be loaded: {state.message}
        </p>
      )}
      {state.status === "ready" && (
        <>
          <p className="ap-note" role="note">
            {state.coverage.direct_measurement_sources} of {state.coverage.sources.length} sources are held, hashed
            direct measurements. The rest are references: inventory coverage is not a measurement.
          </p>
          <table className="ap-table">
            <caption className="subtle">Sources by provider and provenance state</caption>
            <thead>
              <tr>
                <th scope="col">Provider</th>
                <th scope="col">Provenance</th>
                <th scope="col">Sources</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(state.coverage.by_provider).flatMap(([provider, states]) =>
                Object.entries(states).map(([provenance, total]) => (
                  <tr key={`${provider}-${provenance}`} data-provenance-state={provenance}>
                    <th scope="row">{words(provider)}</th>
                    <td>{words(provenance)}</td>
                    <td>{total}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
          <p className="subtle">
            Registry document {state.coverage.provenance.path} · sha256 {shortHash(state.coverage.provenance.sha256)}
          </p>
        </>
      )}
    </section>
  );
}
