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

  it('preserves source lineage and exports enabled catalog geometry', () => {
    const collection = buildVisibleFeatureCollection(
      [{
        id: 'S-1',
        name: 'Ceiba',
        kind: 'port',
        lat: 18.2,
        lng: -65.7,
        sourceIds: ['SRC-1'],
      }],
      [],
      [],
      [{
        id: 'SRC-1',
        name: 'Authoritative registry',
        url: 'https://example.test/source',
        capturedAt: '2026-07-20T00:00:00Z',
        hash: 'abc123',
        lineage: [{ actor: 'registry-adapter', step: 'capture' }],
      }],
      [{
        layer: {
          layer_id: 'municipios',
          label: 'Municipios',
          endpoint: '/geo/municipios.geojson',
          provenance: {
            catalog: 'configs/layer_catalog.yaml',
            geometry_source: 'exported_geojson',
            source_ids: ['manifest:data/tiger/2025/manifest.json'],
            url: 'https://example.test/municipios.zip',
            captured_at: '2026-07-19T00:00:00Z',
            hash: 'def456',
            lineage: [{ actor: 'ingest_tiger_pr.py', step: 'materialize' }],
          },
        },
        collection: {
          type: 'FeatureCollection',
          features: [{
            type: 'Feature',
            id: '72127',
            properties: { GEOID: '72127', name: 'San Juan' },
            geometry: {
              type: 'Polygon',
              coordinates: [[
                [-66.2, 18.3],
                [-66.0, 18.3],
                [-66.0, 18.5],
                [-66.2, 18.3],
              ]],
            },
          }],
        },
      }],
    );

    expect(collection.features).toHaveLength(2);
    expect(collection.features[0].properties).toMatchObject({
      source_ids: ['SRC-1'],
      source_url: 'https://example.test/source',
      captured_at: '2026-07-20T00:00:00Z',
      hash: 'abc123',
    });
    expect(collection.features[1]).toMatchObject({
      id: '72127',
      geometry: { type: 'Polygon' },
      properties: {
        record_type: 'catalog_feature',
        layer_id: 'municipios',
        source_url: 'https://example.test/municipios.zip',
        hash: 'def456',
      },
    });
    const csv = featureCollectionToCsv(collection);
    expect(csv).toContain('catalog_feature');
    expect(csv).toContain('Polygon');
    expect(csv).toContain('def456');
  });
});
