/**
 * Presentation helpers shared by every module.
 *
 * These previously lived in `data/mockData.ts`, which meant six production
 * files imported their formatting utilities from the offline fixture module.
 * Keeping them here leaves `data/mockData.ts` holding only the fixture.
 */

/** Compact currency for dense table cells and KPI stats — `$1.2M`, `$840.0K`. */
export const fmtMoney = (value: number): string => {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
};

/** Look up a record by id in an unindexed array. */
export const byId = <T extends { id: string }>(items: T[], id: string): T | undefined =>
  items.find((item) => item.id === id);
