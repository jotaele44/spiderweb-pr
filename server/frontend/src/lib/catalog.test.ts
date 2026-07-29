import { describe, expect, it } from 'vitest';
import {
  deriveTemporalWindow,
  filterEvents,
  filterSites,
  flattenLayers,
  initialLayerSelection,
  isLayerAvailable,
} from './catalog';
import type { LayerCatalog } from '../types/gis';

const catalog: LayerCatalog = {
  version: 'test',
  families: [
    {
      id: 'admin',
      label: 'Administrative',
      visibility: 'V3',
      layers: [
        { layer_id: 'municipios', label: 'Municipios', runtime_status: 'live' },
        { layer_id: 'tracts', label: 'Tracts', runtime_status: 'unavailable' },
        { layer_id: 'places', label: 'Places', runtime_status: 'empty' },
      ],
    },
  ],
};

describe('catalog helpers', () => {
  it('flattens families and enables only live or explicitly empty layers', () => {
    const layers = flattenLayers(catalog);
    expect(layers).toHaveLength(3);
    expect(layers.filter(isLayerAvailable).map((layer) => layer.layer_id))
      .toEqual(['municipios', 'places']);
    expect([...initialLayerSelection(catalog)]).toEqual(['municipios', 'places']);
  });

  it('searches spatial identity fields without changing the source array', () => {
    const sites = [
      { id: 'S-1', name: 'Carraízo Reservoir', kind: 'water', lat: 18.3, lng: -66.0 },
      { id: 'S-2', name: 'Ceiba Port', kind: 'port', lat: 18.2, lng: -65.7 },
    ];
    expect(filterSites(sites, 'water')).toEqual([sites[0]]);
    expect(sites).toHaveLength(2);
  });

  it('derives and applies an inclusive temporal window', () => {
    const events = [
      { id: 'E-1', kind: 'imagery', at: '2024-01-01', label: 'one' },
      { id: 'E-2', kind: 'report', at: '2024-02-01', label: 'two' },
    ];
    expect(deriveTemporalWindow(events)).toEqual({
      start: '2024-01-01',
      end: '2024-02-01',
    });
    expect(filterEvents(events, { start: '2024-01-15', end: '2024-02-01' }))
      .toEqual([events[1]]);
  });
});
