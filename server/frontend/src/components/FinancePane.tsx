import React, { useEffect, useMemo, useState } from 'react';
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { FederationEmptyState } from '@pr-federation/react';
import { getContracts, Contract } from '../lib/api';
import { useAppStore } from '../state/store';

const money = (v?: number | null) =>
  typeof v === 'number' ? v.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }) : '—';

const col = createColumnHelper<Contract>();
const columns = [
  col.accessor('id', { header: 'ID' }),
  col.accessor('agency', { header: 'Agency', cell: (c) => c.getValue() ?? '—' }),
  col.accessor('vendor', { header: 'Vendor', cell: (c) => c.getValue() ?? '—' }),
  col.accessor('status', { header: 'Status', cell: (c) => c.getValue() ?? '—' }),
  col.accessor('amount', {
    header: () => <span className="fin-num">Amount</span>,
    cell: (c) => <span className="fin-num">{money(c.getValue())}</span>,
  }),
];

/**
 * FinancePane lists contracts (GET /contracts) in a TanStack Table. Selecting a
 * row publishes the contract to the shared store. Wires the previously-unused
 * @tanstack/react-table dependency and the typed API client.
 */
export const FinancePane: React.FC = () => {
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [loading, setLoading] = useState(true);
  const setSelection = useAppStore((s) => s.setSelection);

  useEffect(() => {
    let live = true;
    getContracts().then((rows) => {
      if (!live) return;
      setContracts(rows);
      setLoading(false);
    });
    return () => { live = false; };
  }, []);

  const table = useReactTable({
    data: contracts,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  const body = useMemo(() => {
    if (loading) return <p className="pane__empty">Loading contracts…</p>;
    // Shared federation empty state, `inline` variant — sized to sit beside the
    // loading line above rather than as a full centered block, so the pane's two
    // status messages stay visually matched.
    if (contracts.length === 0) return <FederationEmptyState inline title="No contracts available." />;
    return (
      <table className="fin-table">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th key={h.id}>{flexRender(h.column.columnDef.header, h.getContext())}</th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} onClick={() => setSelection(row.original)}>
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    );
  }, [loading, contracts, table, setSelection]);

  return (
    <section className="pane" aria-label="Finance">
      <div className="pane__header">
        Finance
        <span className="muted">{loading ? 'loading…' : `${contracts.length} contracts`}</span>
      </div>
      <div className="pane__body">{body}</div>
    </section>
  );
};
