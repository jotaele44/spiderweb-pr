import type { Selection, WorkspaceData } from '../types/gis';

function Field({ label, value }: { label: string; value: unknown }) {
  const display = value == null || value === ''
    ? 'Not supplied'
    : typeof value === 'object'
      ? JSON.stringify(value)
      : String(value);
  return (
    <div className="inspector-field">
      <dt>{label}</dt>
      <dd>{display}</dd>
    </div>
  );
}

function ProvenanceFields({
  sourceIds,
  data,
  lineage,
}: {
  sourceIds?: string[];
  data: WorkspaceData;
  lineage?: unknown[];
}) {
  const sources = (sourceIds ?? [])
    .map((sourceId) => data.sources.find((source) => source.id === sourceId))
    .filter((source) => Boolean(source));
  return (
    <>
      <Field label="Source IDs" value={sourceIds} />
      <Field label="Source URL" value={sources.find((source) => source?.url)?.url} />
      <Field
        label="Captured at"
        value={sources.find((source) => source?.capturedAt)?.capturedAt}
      />
      <Field label="Hash" value={sources.find((source) => source?.hash)?.hash} />
      <Field
        label="Lineage"
        value={lineage?.length
          ? lineage
          : sources.flatMap((source) => source?.lineage ?? [])}
      />
    </>
  );
}

export function Inspector({
  data,
  selection,
}: {
  data: WorkspaceData;
  selection: Selection | null;
}) {
  if (!selection) {
    return (
      <aside className="inspector" aria-label="Feature inspector">
        <div className="panel-heading">
          <p>Inspector</p>
          <h2>No selection</h2>
        </div>
        <div className="inspector-body">
          Select a map feature, site, anomaly, or timeline event.
        </div>
      </aside>
    );
  }

  if (selection.kind === 'site') {
    const site = data.sites.find((candidate) => candidate.id === selection.id);
    return (
      <aside className="inspector" aria-label="Feature inspector">
        <div className="panel-heading"><p>Site · {selection.id}</p><h2>{site?.name ?? 'Missing site'}</h2></div>
        <dl className="inspector-body">
          <Field label="Record ID" value={selection.id} />
          <Field label="Type" value={site?.kind} />
          <Field label="Coordinates" value={site ? `${site.lat.toFixed(5)}, ${site.lng.toFixed(5)}` : null} />
          <Field label="Infrastructure" value={site?.infrastructure_class} />
          <Field label="Municipio GEOID" value={site?.municipio_geoid} />
          <Field label="Tract GEOID" value={site?.tract_geoid} />
          <Field label="Evidence tier" value={null} />
          <Field label="Confidence" value={null} />
          <Field label="Source" value="/sites" />
          <ProvenanceFields
            sourceIds={site?.sourceIds}
            lineage={site?.lineage}
            data={data}
          />
          <Field label="Provenance" value={`spiderweb-pr:/sites/${selection.id}`} />
        </dl>
      </aside>
    );
  }

  if (selection.kind === 'event') {
    const event = data.events.find((candidate) => candidate.id === selection.id);
    return (
      <aside className="inspector" aria-label="Feature inspector">
        <div className="panel-heading"><p>Event · {selection.id}</p><h2>{event?.label ?? 'Missing event'}</h2></div>
        <dl className="inspector-body">
          <Field label="Record ID" value={selection.id} />
          <Field label="Event type" value={event?.kind} />
          <Field label="Observed at" value={event?.at} />
          <Field label="Evidence tier" value={event?.tier} />
          <Field label="Confidence" value={null} />
          <Field label="Linked site" value={event?.siteId} />
          <Field label="Source" value="/events" />
          <ProvenanceFields
            sourceIds={event?.sourceIds}
            lineage={event?.lineage}
            data={data}
          />
          <Field label="Provenance" value={`spiderweb-pr:/events/${selection.id}`} />
        </dl>
      </aside>
    );
  }

  if (selection.kind === 'anomaly') {
    const anomaly = data.anomalies.find((candidate) => candidate.id === selection.id);
    return (
      <aside className="inspector" aria-label="Feature inspector">
        <div className="panel-heading"><p>Anomaly · {selection.id}</p><h2>{anomaly?.title ?? 'Missing anomaly'}</h2></div>
        <dl className="inspector-body">
          <Field label="Record ID" value={selection.id} />
          <Field label="Category" value={anomaly?.category} />
          <Field label="Score" value={anomaly?.score} />
          <Field label="Confidence" value={anomaly?.confidence} />
          <Field label="Evidence tier" value={null} />
          <Field label="Summary" value={anomaly?.summary} />
          <Field label="Contradictions" value={anomaly?.contradictions?.join(' · ')} />
          <Field label="Linked site" value={anomaly?.siteId} />
          <Field label="Source" value="/anomalies" />
          <ProvenanceFields
            sourceIds={anomaly?.sourceIds}
            lineage={anomaly?.lineage}
            data={data}
          />
          <Field label="Provenance" value={`spiderweb-pr:/anomalies/${selection.id}`} />
        </dl>
      </aside>
    );
  }

  const catalogLayer = data.catalog?.families
    .flatMap((family) => family.layers)
    .find((layer) => layer.layer_id === selection.layerId);
  return (
    <aside className="inspector" aria-label="Feature inspector">
      <div className="panel-heading"><p>Layer · {selection.layerId}</p><h2>{selection.id}</h2></div>
      <dl className="inspector-body">
        <Field label="Record ID" value={selection.id} />
        {Object.entries(selection.properties).slice(0, 16)
          .map(([key, value]) => <Field key={key} label={key} value={value} />)}
        <Field label="Source" value={`/geo/${selection.layerId}.geojson`} />
        <Field label="Catalog provenance" value={catalogLayer?.provenance?.catalog} />
        <Field label="Geometry source" value={catalogLayer?.provenance?.geometry_source} />
        <Field label="Source IDs" value={selection.properties.source_ids ?? catalogLayer?.provenance?.source_ids} />
        <Field label="Source URL" value={selection.properties.source_url ?? catalogLayer?.provenance?.url} />
        <Field label="Captured at" value={selection.properties.captured_at ?? catalogLayer?.provenance?.captured_at} />
        <Field label="Hash" value={selection.properties.hash ?? catalogLayer?.provenance?.hash} />
        <Field label="Lineage" value={selection.properties.lineage ?? catalogLayer?.provenance?.lineage} />
        <Field label="Provenance" value={`spiderweb-pr:/geo/${selection.layerId}/${selection.id}`} />
      </dl>
    </aside>
  );
}
