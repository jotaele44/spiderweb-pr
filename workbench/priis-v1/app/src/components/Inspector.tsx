import { byId, fmtMoney } from "../data/mockData";
import type { PriisData, Selection, SpatialFilter, TrackPoint } from "../types/priis";
import { AnomalyScore, ConfidenceMeter, ContradictionFlag, Pill, TierBadge } from "./Badges";
import { sitesContainedIn } from "../lib/selectors";

function SpatialFilterCard({
  data,
  filter,
  clear,
}: {
  data: PriisData;
  filter: SpatialFilter;
  clear: () => void;
}) {
  // null sentinel = filter kind isn't yet joined to `sites`; show the
  // filter without counts rather than misleading zeros.
  const sitesInFilter = sitesContainedIn(data.sites, filter);
  const siteIds = new Set(sitesInFilter?.map((s) => s.id));
  const contractsInFilter = sitesInFilter
    ? data.contracts.filter((c) => siteIds.has(c.site))
    : null;
  const anomaliesInFilter = sitesInFilter
    ? data.anomalies.filter((a) => siteIds.has(a.siteId))
    : null;

  return (
    <div className="card" style={{ borderLeft: "3px solid var(--warn)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 6 }}>
        <div>
          <div className="subtle mono">GEOGRAPHY FILTER</div>
          <b>{filter.label}</b>
          <div className="subtle mono" style={{ fontSize: "0.7rem" }}>
            {filter.kind} · {filter.geoid}
          </div>
        </div>
        <button className="act" onClick={clear}>CLEAR</button>
      </div>
      {sitesInFilter ? (
        <div className="row" style={{ marginTop: 6, gap: 10 }}>
          <span><b>{sitesInFilter.length}</b> sites</span>
          <span><b>{contractsInFilter?.length ?? 0}</b> contracts</span>
          <span><b>{anomaliesInFilter?.length ?? 0}</b> anomalies</span>
        </div>
      ) : (
        <p className="subtle" style={{ marginTop: 6, fontSize: "0.75rem" }}>
          {filter.kind} polygons aren't joined to sites yet; filter is informational only.
        </p>
      )}
    </div>
  );
}

/**
 * Compact summary of an ADS-B track — point count, time span, altitude
 * range. Returns null while still loading or when no track exists yet.
 */
function FlightTrackCard({ track }: { track: TrackPoint[] | null }) {
  if (track === null) return null;
  if (track.length === 0) {
    return (
      <div className="card">
        <h3>ADS-B track</h3>
        <p className="subtle">
          No track ingested for this flight. Run
          {" "}
          <span className="mono">scripts/parse_adsb_archive.py</span>
          {" "}
          to populate.
        </p>
      </div>
    );
  }
  const altitudes = track
    .map((p) => p.altitudeFt)
    .filter((a): a is number => typeof a === "number");
  const minAlt = altitudes.length ? Math.min(...altitudes) : null;
  const maxAlt = altitudes.length ? Math.max(...altitudes) : null;
  const startAt = track[0].at ?? new Date(track[0].ts * 1000).toISOString();
  const endAt = track[track.length - 1].at ?? new Date(track[track.length - 1].ts * 1000).toISOString();
  return (
    <div className="card">
      <h3>ADS-B track</h3>
      <p className="mono">
        {track.length} points · {startAt} → {endAt}
      </p>
      {minAlt !== null && maxAlt !== null && (
        <p className="mono">altitude {minAlt}–{maxAlt} ft</p>
      )}
      <p className="subtle" style={{ fontSize: "0.75rem", marginTop: 4 }}>
        Track is rendered on the Spatial map.
      </p>
    </div>
  );
}

function PinButton({
  selection,
  watchlist,
  pin,
  unpin,
}: {
  selection: Selection;
  watchlist: Selection[];
  pin: (s: Selection) => void;
  unpin: (s: Selection) => void;
}) {
  const isPinned = watchlist.some(
    (w) => w.kind === selection.kind && w.id === selection.id,
  );
  return (
    <button
      className="act"
      style={{ fontSize: "0.7rem" }}
      title={isPinned ? "Remove from watchlist" : "Pin to watchlist"}
      onClick={() => (isPinned ? unpin(selection) : pin(selection))}
    >
      {isPinned ? "★ PINNED" : "☆ PIN"}
    </button>
  );
}

export function Inspector({
  data,
  selection,
  setSelection,
  spatialFilter,
  clearSpatialFilter,
  flightTrack,
  watchlist,
  pinToWatchlist,
  unpinFromWatchlist,
}: {
  data: PriisData;
  selection: Selection | null;
  setSelection: (selection: Selection) => void;
  spatialFilter: SpatialFilter | null;
  clearSpatialFilter: () => void;
  flightTrack: TrackPoint[] | null;
  watchlist: Selection[];
  pinToWatchlist: (selection: Selection) => void;
  unpinFromWatchlist: (selection: Selection) => void;
}) {
  const pinAffordance = (sel: Selection) => (
    <PinButton
      selection={sel}
      watchlist={watchlist}
      pin={pinToWatchlist}
      unpin={unpinFromWatchlist}
    />
  );
  const filterCard = spatialFilter ? (
    <SpatialFilterCard data={data} filter={spatialFilter} clear={clearSpatialFilter} />
  ) : null;

  if (!selection) {
    return (
      <aside className="inspector">
        <div className="inspector-head"><div className="subtle mono">INSPECTOR</div><h2>{spatialFilter ? spatialFilter.label : "No selection"}</h2></div>
        <div className="inspector-body">
          {filterCard}
          <p>Select a contract, site, anomaly, vendor, or event.</p>
        </div>
      </aside>
    );
  }

  if (selection.kind === "anomaly") {
    const anomaly = byId(data.anomalies, selection.id);
    if (!anomaly) return <Missing selection={selection} />;
    const site = byId(data.sites, anomaly.siteId);
    return (
      <aside className="inspector">
        <div className="inspector-head">
          <div className="subtle mono">ANOMALY · {anomaly.id}</div>
          <h2>{anomaly.title}</h2>
          <div className="row"><AnomalyScore score={anomaly.score} /><Pill tone={anomaly.band === "hi" ? "alert" : "warn"}>{anomaly.category}</Pill>{pinAffordance({ kind: "anomaly", id: anomaly.id })}</div>
        </div>
        <div className="inspector-body">
          {filterCard}
          <p className="desc">{anomaly.summary}</p>
          <ConfidenceMeter value={anomaly.confidence} />
          <ContradictionFlag items={anomaly.contradictions} />
          {site && <button className="act" onClick={() => setSelection({ kind: "site", id: site.id })}>Open site · {site.name}</button>}
          <div className="card">
            <h3>Factors</h3>
            <ul>{anomaly.factors.map((factor) => <li key={`${factor.tag}-${factor.note}`}><b>{factor.tag}</b> — {factor.note}</li>)}</ul>
          </div>
          <div className="card">
            <h3>Linked contracts</h3>
            {anomaly.contracts.map((id) => {
              const contract = byId(data.contracts, id);
              return contract ? <button className="navbtn" key={id} onClick={() => setSelection({ kind: "contract", id })}><span>{id}</span><span>{fmtMoney(contract.amount)}</span></button> : null;
            })}
          </div>
        </div>
      </aside>
    );
  }

  if (selection.kind === "contract") {
    const contract = byId(data.contracts, selection.id);
    if (!contract) return <Missing selection={selection} />;
    const agency = byId(data.agencies, contract.agency);
    const vendor = byId(data.vendors, contract.vendor);
    const site = byId(data.sites, contract.site);
    return (
      <aside className="inspector">
        <div className="inspector-head">
          <div className="subtle mono">CONTRACT · {contract.id}</div>
          <h2>{fmtMoney(contract.amount)}</h2>
          <div className="row"><TierBadge tier={contract.tier} /><Pill tone={contract.status === "flagged" ? "alert" : contract.status === "amended" ? "warn" : "ok"}>{contract.status}</Pill>{pinAffordance({ kind: "contract", id: contract.id })}</div>
        </div>
        <div className="inspector-body">
          {filterCard}
          <div className="card"><h3>Record</h3><p>{contract.note ?? "No note."}</p><p className="mono">signed {contract.signed}</p></div>
          {agency && <button className="act" onClick={() => setSelection({ kind: "agency", id: agency.id })}>Agency · {agency.code}</button>}
          {vendor && <button className="act" onClick={() => setSelection({ kind: "vendor", id: vendor.id })}>Vendor · {vendor.name}</button>}
          {site && <button className="act" onClick={() => setSelection({ kind: "site", id: site.id })}>Site · {site.name}</button>}
        </div>
      </aside>
    );
  }

  if (selection.kind === "site") {
    const site = byId(data.sites, selection.id);
    if (!site) return <Missing selection={selection} />;
    const contracts = data.contracts.filter((contract) => contract.site === site.id);
    const anomalies = data.anomalies.filter((anomaly) => anomaly.siteId === site.id);
    return (
      <aside className="inspector">
        <div className="inspector-head"><div className="subtle mono">SITE · {site.id}</div><h2>{site.name}</h2><div className="row"><Pill tone={site.sensitive ? "alert" : "info"}>{site.kind}</Pill>{pinAffordance({ kind: "site", id: site.id })}</div></div>
        <div className="inspector-body">
          {filterCard}
          <div className="card"><h3>Coordinates</h3><p className="mono">{site.lat.toFixed(4)}, {site.lng.toFixed(4)}</p></div>
          {(site.municipio_geoid || site.tract_geoid || site.zcta_geoid) && (
            <div className="card">
              <h3>TIGER GEOIDs</h3>
              {site.municipio_geoid && <p className="mono">municipio · <b>{site.municipio_geoid}</b></p>}
              {site.tract_geoid     && <p className="mono">tract · <b>{site.tract_geoid}</b></p>}
              {site.zcta_geoid      && <p className="mono">zcta · <b>{site.zcta_geoid}</b></p>}
            </div>
          )}
          <div className="card"><h3>Contracts</h3>{contracts.map((contract) => <button key={contract.id} className="navbtn" onClick={() => setSelection({ kind: "contract", id: contract.id })}><span>{contract.id}</span><span>{fmtMoney(contract.amount)}</span></button>)}</div>
          <div className="card"><h3>Anomalies</h3>{anomalies.map((anomaly) => <button key={anomaly.id} className="navbtn" onClick={() => setSelection({ kind: "anomaly", id: anomaly.id })}><span>{anomaly.id}</span><span>{Math.round(anomaly.score * 100)}</span></button>)}</div>
        </div>
      </aside>
    );
  }

  if (selection.kind === "vendor") {
    const vendor = byId(data.vendors, selection.id);
    if (!vendor) return <Missing selection={selection} />;
    const contracts = data.contracts.filter((contract) => contract.vendor === vendor.id);
    return (
      <aside className="inspector">
        <div className="inspector-head"><div className="subtle mono">VENDOR · {vendor.id}</div><h2>{vendor.name}</h2><div className="row"><TierBadge tier={vendor.tier} /><Pill tone={vendor.risk > 0.7 ? "alert" : vendor.risk > 0.55 ? "warn" : "ok"}>risk {vendor.risk.toFixed(2)}</Pill>{pinAffordance({ kind: "vendor", id: vendor.id })}</div></div>
        <div className="inspector-body">
          {filterCard}
          <div className="card"><h3>Linked awards</h3>{contracts.map((contract) => <button key={contract.id} className="navbtn" onClick={() => setSelection({ kind: "contract", id: contract.id })}><span>{contract.id}</span><span>{fmtMoney(contract.amount)}</span></button>)}</div>
        </div>
      </aside>
    );
  }

  const event = selection.kind === "event" ? byId(data.events, selection.id) : undefined;
  if (event) {
    return (
      <aside className="inspector">
        <div className="inspector-head"><div className="subtle mono">EVENT · {event.id}</div><h2>{event.label}</h2><div className="row">{event.tier && <TierBadge tier={event.tier} />}<Pill>{event.kind}</Pill>{pinAffordance({ kind: "event", id: event.id })}</div></div>
        <div className="inspector-body">
          {filterCard}
          {event.kind === "flight" && <FlightTrackCard track={flightTrack} />}
          <button className="act" onClick={() => setSelection({ kind: "site", id: event.siteId })}>Open linked site</button>
          {event.refId && <button className="act" onClick={() => setSelection({ kind: "contract", id: event.refId ?? "" })}>Open referenced record</button>}
        </div>
      </aside>
    );
  }

  return <Missing selection={selection} />;
}

function Missing({ selection }: { selection: Selection }) {
  return (
    <aside className="inspector">
      <div className="inspector-head"><div className="subtle mono">INSPECTOR</div><h2>Missing record</h2></div>
      <div className="inspector-body"><p>{selection.kind}/{selection.id} is not present in the fixture dataset.</p></div>
    </aside>
  );
}
