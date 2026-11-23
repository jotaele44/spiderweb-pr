import { describe, expect, it } from 'vitest';
import { priisData } from '../data/mockData';
import { validDataset } from './localDataset';

describe('local dataset admission', () => {
  it('accepts the declared demo corpus without modifying rows', () => {
    const before = JSON.stringify(priisData);
    expect(validDataset(priisData)).toBe(true);
    expect(JSON.stringify(priisData)).toBe(before);
  });
  it('rejects duplicate stable IDs rather than selecting or merging rows', () => {
    expect(validDataset({ ...priisData, agencies: [priisData.agencies[0], priisData.agencies[0]] })).toBe(false);
  });
  it('rejects malformed rows instead of silently dropping them', () => {
    expect(validDataset({ ...priisData, agencies: [{}] })).toBe(false);
    expect(validDataset({ ...priisData, contracts: null })).toBe(false);
  });
  it('rejects malformed watchlist references', () => {
    expect(validDataset({ ...priisData, watchlist: [{ kind: 'invented', id: 'a' }] })).toBe(false);
  });
});
