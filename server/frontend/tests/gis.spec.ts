import { expect, test, type Page } from '@playwright/test';

const site = {
  id: 'S-CARRAIZO',
  name: 'Carraízo Reservoir',
  kind: 'reservoir',
  lat: 18.327,
  lng: -66.014,
  sensitive: false,
  infrastructure_class: 'water',
  municipio_geoid: '72127',
};

async function mockApi(page: Page): Promise<void> {
  await page.route('**/health', (route) => route.fulfill({
    json: { status: 'ok', db_exists: true, table_count: 9 },
  }));
  await page.route('**/sites', (route) => route.fulfill({ json: [site] }));
  await page.route('**/events', (route) => route.fulfill({
    json: [{
      id: 'E-IMAGERY-1',
      kind: 'imagery',
      at: '2026-07-20',
      siteId: site.id,
      label: 'Shoreline change observation',
      tier: 'T1',
    }],
  }));
  await page.route('**/anomalies', (route) => route.fulfill({
    json: [{
      id: 'A-SPATIAL-1',
      title: 'Reservoir change cluster',
      category: 'spatial',
      score: 0.81,
      band: 'hi',
      siteId: site.id,
      summary: 'Multiple spatial observations require review.',
      confidence: 3,
      contradictions: [],
    }],
  }));
  await page.route('**/sources', (route) => route.fulfill({
    json: [{ id: 'SRC-IMAGERY', name: 'Imagery ledger', tier: 'T1', status: 'online' }],
  }));
  await page.route('**/catalog', (route) => route.fulfill({
    json: {
      version: 'test',
      families: [{
        id: 'admin_geographies',
        label: 'Administrative Geographies',
        visibility: 'V3',
        layers: [{
          layer_id: 'municipios',
          label: 'Municipios',
          runtime_status: 'live',
          endpoint: '/geo/municipios.geojson',
        }],
      }],
    },
  }));
  await page.route('**/geo/municipios.geojson', (route) => route.fulfill({
    json: {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        properties: { id: 'M-127', name: 'San Juan', GEOID: '72127' },
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [-66.15, 18.3],
            [-65.95, 18.3],
            [-65.95, 18.5],
            [-66.15, 18.5],
            [-66.15, 18.3],
          ]],
        },
      }],
    },
  }));
  await page.route('https://tile.openstreetmap.org/**', (route) => route.abort());
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
});

test('opens on the canonical GIS map with catalog layers and no airspace navigation', async ({ page }) => {
  await expect(page).toHaveTitle(/Spiderweb/);
  await expect(page.getByRole('heading', { name: 'Spatial intelligence' })).toBeVisible();
  await expect(page.getByTestId('gis-map')).toBeVisible();
  await expect(page.getByRole('button', { name: /Municipios/ })).toBeEnabled();
  await expect(page.getByRole('button', { name: /Carraízo Reservoir/ })).toBeVisible();
  await expect(page.getByText(/FR24/i)).toHaveCount(0);
  await expect(page.getByText(/Aircraft Catalog/i)).toHaveCount(0);
});

test('inspects a spatial marker with source and provenance', async ({ page }) => {
  await page.getByRole('button', { name: /Carraízo Reservoir/ }).click();
  await expect(page.getByRole('complementary', { name: 'Feature inspector' }))
    .toContainText('S-CARRAIZO');
  await expect(page.getByRole('complementary', { name: 'Feature inspector' }))
    .toContainText('spiderweb-pr:/anomalies/A-SPATIAL-1');
});

test('exports the visible spatial selection as GeoJSON', async ({ page }) => {
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export GeoJSON' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^spiderweb-spatial-.*\.geojson$/);
});
