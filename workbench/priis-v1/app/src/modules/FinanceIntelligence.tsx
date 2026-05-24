import { useMemo, useState } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { byId, fmtMoney } from "../data/mockData";
import type { Contract, PriisData, Selection } from "../types/priis";
import { Pill, TierBadge } from "../components/Badges";
import { exportContractsCsv } from "../export/csvExport";

const colHelper = createColumnHelper<Contract>();

export function FinanceIntelligence({
  data,
  selection,
  setSelection,
}: {
  data: PriisData;
  selection: Selection | null;
  setSelection: (selection: Selection) => void;
}) {
  const [sorting, setSorting] = useState<SortingState>([{ id: "amount", desc: true }]);
  const [globalFilter, setGlobalFilter] = useState("");

  const total = data.contracts.reduce((sum, c) => sum + c.amount, 0);
  const vendorTotals = useMemo(
    () =>
      data.vendors
        .map((v) => ({
          vendor: v,
          total: data.contracts.filter((c) => c.vendor === v.id).reduce((s, c) => s + c.amount, 0),
        }))
        .filter((r) => r.total > 0)
        .sort((a, b) => b.total - a.total),
    [data],
  );

  const columns = useMemo(
    () => [
      colHelper.accessor("id", { header: "ID", cell: (i) => <span className="mono">{i.getValue()}</span> }),
      colHelper.accessor("signed", { header: "Signed", cell: (i) => <span className="mono">{i.getValue()}</span> }),
      colHelper.accessor("agency", {
        header: "Agency",
        cell: (i) => <span className="mono">{byId(data.agencies, i.getValue())?.code ?? i.getValue()}</span>,
      }),
      colHelper.accessor("vendor", {
        header: "Vendor",
        cell: (i) => byId(data.vendors, i.getValue())?.name ?? i.getValue(),
      }),
      colHelper.accessor("site", {
        header: "Site",
        cell: (i) => byId(data.sites, i.getValue() ?? "")?.name ?? i.getValue(),
      }),
      colHelper.accessor("amount", {
        header: "Amount",
        cell: (i) => <span className="num mono">{fmtMoney(i.getValue())}</span>,
      }),
      colHelper.accessor("status", {
        header: "Status",
        cell: (i) => (
          <Pill tone={i.getValue() === "flagged" ? "alert" : i.getValue() === "amended" ? "warn" : "ok"}>
            {i.getValue()}
          </Pill>
        ),
      }),
      colHelper.accessor("tier", {
        header: "Tier",
        cell: (i) => <TierBadge tier={i.getValue()} />,
      }),
    ],
    [data],
  );

  const table = useReactTable({
    data: data.contracts,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h1>Finance Intelligence</h1>
          <span className="subtle">Contracts · vendors · awards · amendments</span>
        </div>
        <div className="row" style={{ gap: "0.5rem" }}>
          <input
            className="subtle mono"
            style={{ border: "1px solid var(--line)", borderRadius: "3px", padding: "2px 6px", background: "var(--surface-2)", color: "inherit", fontSize: "0.8rem" }}
            placeholder="filter…"
            value={globalFilter}
            onChange={(e) => setGlobalFilter(e.target.value)}
          />
          <button className="act" onClick={() => exportContractsCsv(data)}>
            EXPORT CSV
          </button>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", height: "100%", minHeight: 0 }}>
        <div className="panel-grid">
          <div className="cards">
            <div className="card">
              <h3>Total awarded</h3>
              <div className="stat">{fmtMoney(total)}</div>
              <div className="delta">12m fixture window</div>
            </div>
            <div className="card">
              <h3>Flagged</h3>
              <div className="stat">{data.contracts.filter((c) => c.status === "flagged").length}</div>
              <div className="delta">requires contradiction check</div>
            </div>
            <div className="card">
              <h3>Amended</h3>
              <div className="stat">{data.contracts.filter((c) => c.status === "amended").length}</div>
              <div className="delta">scope review queue</div>
            </div>
            <div className="card">
              <h3>Top vendor</h3>
              <div className="stat">{vendorTotals[0]?.vendor.id}</div>
              <div className="delta">{fmtMoney(vendorTotals[0]?.total ?? 0)}</div>
            </div>
          </div>
          <div className="table-wrap">
            <table className="dtable">
              <thead>
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    {hg.headers.map((header) => (
                      <th
                        key={header.id}
                        style={{ cursor: header.column.getCanSort() ? "pointer" : undefined }}
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getIsSorted() === "asc" ? " ↑" : header.column.getIsSorted() === "desc" ? " ↓" : ""}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.map((row) => (
                  <tr
                    key={row.id}
                    data-active={selection?.kind === "contract" && selection.id === row.original.id}
                    onClick={() => setSelection({ kind: "contract", id: row.original.id })}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <aside className="layer-panel">
          <h3>Vendor concentration</h3>
          <div className="col">
            {vendorTotals.map(({ vendor, total: vt }) => (
              <button key={vendor.id} className="navbtn" onClick={() => setSelection({ kind: "vendor", id: vendor.id })}>
                <span>{vendor.name}</span>
                <span className="mono">{fmtMoney(vt)}</span>
              </button>
            ))}
          </div>
        </aside>
      </div>
    </section>
  );
}
