import { describe, expect, it } from 'vitest';
import { buildVisibleFeatureCollection, featureCollectionToCsv } from './export';

describe('spatial export', () => {
  it('exports visible records with coordinates and provenance', () => {
    const sites = [
      { id: 'S-1', name: 'Carraízo Reservoir', kind: 'water', lat: 18.31, lng: -66.02 },
    ];
    const collection = buildVisibleFeatureCollection(
      sites,
      [{ id: 'E-1', kind: 'imagery', at: '2024-01-03', siteId: 'S-1', label: 'Change', tier: 'T1' }],
      [{
        id: 'A-1',
        title: 'Spatial signal',
        category: 'spatial',
        score: 0.8,
        band: 'hi',
        siteId: 'S-1',
        confidence: 3,
      }],
    );
    expect(collection.features).toHaveLength(3);
    expect(collection.features[1].properties).toMatchObject({
      record_id: 'E-1',
      evidence_tier: 'T1',
      provenance: 'spiderweb-pr:/events/E-1',
    });
    expect(collection.features[1].id).toBe('E-1');
    expect(collection.features[1].geometry?.coordinates).toEqual([-66.02, 18.31]);
  });

  it('serializes the provenance columns to CSV', () => {
    const collection = buildVisibleFeatureCollection(
      [{ id: 'S-1', name: 'Ceiba, East', kind: 'port', lat: 18.2, lng: -65.7 }],
      [],
      [],
    );
    const csv = featureCollectionToCsv(collection);
    expect(csv).toContain('record_id,record_type');
    expect(csv).toContain('spiderweb-pr:/sites/S-1');
    expect(csv).toContain('-65.7,18.2');
  });
});
