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
import { fmtMoney } from "../lib/format";
import type { Contract, PriisData, Selection } from "../types/priis";
import { Pill, TierBadge, contractStatusTone } from "../components/Badges";
import { Card } from "../components/Card";
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

  const agenciesById = useMemo(() => new Map(data.agencies.map((agency) => [agency.id, agency])), [data.agencies]);
  const vendorsById = useMemo(() => new Map(data.vendors.map((vendor) => [vendor.id, vendor])), [data.vendors]);
  const sitesById = useMemo(() => new Map(data.sites.map((site) => [site.id, site])), [data.sites]);

  const total = useMemo(() => data.contracts.reduce((sum, c) => sum + c.amount, 0), [data.contracts]);
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
        cell: (i) => <span className="mono">{agenciesById.get(i.getValue())?.code ?? i.getValue()}</span>,
      }),
      colHelper.accessor("vendor", {
        header: "Vendor",
        cell: (i) => vendorsById.get(i.getValue())?.name ?? i.getValue(),
      }),
      colHelper.accessor("site", {
        header: "Site",
        cell: (i) => sitesById.get(i.getValue() ?? "")?.name ?? i.getValue(),
      }),
      colHelper.accessor("amount", {
        header: "Amount",
        cell: (i) => <span className="num mono">{fmtMoney(i.getValue())}</span>,
      }),
      colHelper.accessor("status", {
        header: "Status",
        cell: (i) => <Pill tone={contractStatusTone(i.getValue())}>{i.getValue()}</Pill>,
      }),
      colHelper.accessor("tier", {
        header: "Tier",
        cell: (i) => <TierBadge tier={i.getValue()} />,
      }),
    ],
    [agenciesById, sitesById, vendorsById],
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
    // TanStack's default global filter sees the raw foreign-key values (V-1024,
    // A-0007, S-0042), while the table renders the joined vendor/agency/site
    // labels. That made a visible value such as "Caribe" impossible to search.
    // Search the same semantic values the operator can actually see, preserving
    // raw ids as additional discovery terms rather than treating them as the
    // only searchable representation.
    globalFilterFn: (row, _columnId, filterValue) => {
      const contract = row.original;
      const agency = agenciesById.get(contract.agency);
      const vendor = vendorsById.get(contract.vendor);
      const site = sitesById.get(contract.site ?? "");
      const haystack = [
        contract.id,
        contract.signed,
        contract.agency,
        agency?.code,
        agency?.name,
        contract.vendor,
        vendor?.name,
        contract.site,
        site?.name,
        contract.amount,
        fmtMoney(contract.amount),
        contract.status,
        contract.tier,
      ]
        .filter((value) => value !== undefined && value !== null)
        .join(" ")
        .toLocaleLowerCase();
      return haystack.includes(String(filterValue ?? "").trim().toLocaleLowerCase());
    },
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
            className="subtle mono table-filter"
            aria-label="Filter contracts"
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
            <Card title="Total awarded" stat={fmtMoney(total)} delta={`${data.contracts.length} contracts`} />
            <Card title="Flagged" stat={data.contracts.filter((c) => c.status === "flagged").length} delta="requires contradiction check" />
            <Card title="Amended" stat={data.contracts.filter((c) => c.status === "amended").length} delta="scope review queue" />
            <Card title="Top vendor" stat={vendorTotals[0]?.vendor.name ?? "—"} delta={fmtMoney(vendorTotals[0]?.total ?? 0)} />
          </div>
          <div className="table-wrap">
            <table className="dtable" role="grid" aria-label="Contracts">
              <thead>
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    {hg.headers.map((header) => {
                      const sorted = header.column.getIsSorted();
                      const canSort = header.column.getCanSort();
                      return (
                        <th
                          key={header.id}
                          aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : canSort ? "none" : undefined}
                        >
                          {canSort ? (
                            <button type="button" className="th-sort" onClick={header.column.getToggleSortingHandler()}>
                              {flexRender(header.column.columnDef.header, header.getContext())}
                              <span aria-hidden="true">{sorted === "asc" ? " ↑" : sorted === "desc" ? " ↓" : ""}</span>
                            </button>
                          ) : (
                            flexRender(header.column.columnDef.header, header.getContext())
                          )}
                        </th>
                      );
                    })}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.length === 0 ? (
                  <tr>
                    <td colSpan={columns.length} className="subtle" style={{ padding: 24, textAlign: "center" }}>
                      {globalFilter ? `No contracts match “${globalFilter}”.` : "No contracts in the current dataset."}
                    </td>
                  </tr>
                ) : (
                  table.getRowModel().rows.map((row) => {
                    const active = selection?.kind === "contract" && selection.id === row.original.id;
                    const select = () => setSelection({ kind: "contract", id: row.original.id });
                    return (
                      <tr
                        key={row.id}
                        data-active={active}
                        tabIndex={0}
                        aria-selected={active}
                        aria-label={`Contract ${row.original.id}`}
                        onClick={select}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(); } }}
                      >
                        {row.getVisibleCells().map((cell) => (
                          <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                        ))}
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
        <aside className="layer-panel">
          <h2>Vendor concentration</h2>
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
