import type { ModuleId, PriisData, Selection } from "../types/priis";
import { TierBadge, Pill, sourceStatusTone } from "./Badges";
import { RailSection } from "./RailSection";

const modules: { id: ModuleId; label: string; code: string }[] = [
  { id: "command", label: "Command", code: "00" },
  { id: "finance", label: "Finance", code: "01" },
  { id: "spatial", label: "Spatial", code: "02" },
  { id: "anomaly", label: "Anomaly", code: "03" },
  { id: "graph", label: "Graph", code: "04" },
  { id: "query", label: "Query", code: "05" }
];

export function LeftRail({
  data,
  moduleId,
  setModule,
  activeInvestigation,
  setActiveInvestigation,
  setSelection
}: {
  data: PriisData;
  moduleId: ModuleId;
  setModule: (id: ModuleId) => void;
  activeInvestigation: string;
  setActiveInvestigation: (id: string) => void;
  setSelection: (selection: Selection) => void;
}) {
  return (
    <aside className="rail">
      <RailSection title="Modules">
        {modules.map((mod) => (
          <button key={mod.id} className="navbtn" data-active={mod.id === moduleId} onClick={() => setModule(mod.id)}>
            <span>{mod.label}</span><span className="mono">{mod.code}</span>
          </button>
        ))}
      </RailSection>

      <RailSection title="Investigations" isEmpty={data.investigations.length === 0} empty="No investigations">
        {data.investigations.map((inv) => (
          <button key={inv.id} className="navbtn" data-active={inv.id === activeInvestigation} onClick={() => setActiveInvestigation(inv.id)}>
            <span>{inv.id}</span><span>{inv.status}</span>
          </button>
        ))}
      </RailSection>

      <RailSection title="Sources" isEmpty={data.sources.length === 0} empty="No sources reporting">
        {data.sources.map((source) => (
          <div className="source-row" key={source.id}>
            <span>{source.name}</span>
            <span className="row"><TierBadge tier={source.tier} /><Pill tone={sourceStatusTone(source.status)}>{source.status}</Pill></span>
          </div>
        ))}
      </RailSection>

      <RailSection title="Watchlist" isEmpty={data.watchlist.length === 0} empty="Watchlist empty">
        {data.watchlist.map((item) => (
          <button key={`${item.kind}-${item.id}`} className="navbtn" onClick={() => setSelection(item)}>
            <span>{item.kind}</span><span className="mono">{item.id}</span>
          </button>
        ))}
      </RailSection>
    </aside>
  );
}
