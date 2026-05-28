/**
 * Optional Contract-Finance dashboard layer.
 *
 * Reads window.contractFinanceDashboardData, populated by dashboard.html from
 * ../outputs/contract_finance_layer_report.json and
 * ../outputs/contract_finance_scored_overlay.geojson.
 */

const ContractFinancePanel = ({ data }) => {
  const [visible, setVisible] = React.useState(true);
  if (!data || !data.report) return null;

  const report = data.report || {};
  const overlay = data.overlay || { features: [] };
  const features = Array.isArray(overlay.features) ? overlay.features : [];
  const top = [...features]
    .sort((a, b) => ((b.properties || {}).spiderweb_score || 0) - ((a.properties || {}).spiderweb_score || 0))
    .slice(0, 8);

  const byTier = report.by_tier || {};
  const byType = report.by_feature_type || {};
  const fmtMoney = (value) => {
    const n = Number(value || 0);
    if (!Number.isFinite(n)) return "$0";
    return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  };

  return (
    <div className="fixed bottom-4 right-4 z-50 w-[420px] max-w-[calc(100vw-2rem)]">
      <div className="bg-white rounded-xl shadow-2xl border border-gray-200 overflow-hidden">
        <button
          onClick={() => setVisible(!visible)}
          className="w-full px-4 py-3 bg-gray-900 text-white flex items-center justify-between text-sm font-semibold"
        >
          <span>Contract-Finance Layer</span>
          <span className="text-xs text-gray-300">{visible ? "hide" : "show"}</span>
        </button>
        {visible && (
          <div className="p-4 space-y-4 max-h-[70vh] overflow-auto">
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="bg-gray-50 rounded-lg p-2">
                <div className="text-lg font-bold text-gray-800">{report.record_count || features.length || 0}</div>
                <div className="text-[11px] text-gray-500">records</div>
              </div>
              <div className="bg-gray-50 rounded-lg p-2">
                <div className="text-lg font-bold text-gray-800">{byTier.T1 || 0}</div>
                <div className="text-[11px] text-gray-500">T1</div>
              </div>
              <div className="bg-gray-50 rounded-lg p-2">
                <div className="text-lg font-bold text-gray-800">{report.status || "—"}</div>
                <div className="text-[11px] text-gray-500">status</div>
              </div>
            </div>

            <div>
              <h3 className="text-xs font-semibold text-gray-700 mb-2">Feature mix</h3>
              <div className="flex flex-wrap gap-2">
                {Object.entries(byType).map(([k, v]) => (
                  <span key={k} className="px-2 py-1 bg-blue-50 text-blue-700 rounded text-xs">
                    {k}: {v}
                  </span>
                ))}
              </div>
            </div>

            <div>
              <h3 className="text-xs font-semibold text-gray-700 mb-2">Top scored records</h3>
              <div className="space-y-2">
                {top.length === 0 ? (
                  <p className="text-xs text-gray-400">No contract-finance features loaded.</p>
                ) : top.map((feature, i) => {
                  const p = feature.properties || {};
                  const entity = p.entity || {};
                  return (
                    <div key={p.record_id || i} className="border border-gray-100 rounded-lg p-2 text-xs">
                      <div className="flex gap-2 items-center mb-1">
                        <span className="font-mono text-blue-700">{p.record_id || "—"}</span>
                        <span className="ml-auto font-semibold text-gray-700">score {p.spiderweb_score ?? "—"}</span>
                      </div>
                      <div className="text-gray-700 truncate">{entity.normalized_name || p.entity_id || "Unknown entity"}</div>
                      <div className="text-gray-500 flex justify-between mt-1">
                        <span>{p.municipality_name || "municipality unknown"}</span>
                        <span>{fmtMoney(p.amount)}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const mountContractFinancePanel = () => {
  const data = window.contractFinanceDashboardData;
  if (!data) return;
  const target = document.getElementById("contract-finance-root");
  if (!target) return;
  ReactDOM.render(<ContractFinancePanel data={data} />, target);
};

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountContractFinancePanel);
  } else {
    mountContractFinancePanel();
  }
}
