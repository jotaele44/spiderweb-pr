import fs from 'node:fs'
import path from 'node:path'
import { chromium, firefox, webkit } from 'playwright'

const BASE_URL = process.env.GUI_BASE_URL || 'http://127.0.0.1:5173'
const outDir = path.resolve(process.env.GUI_ARTIFACT_DIR || 'artifacts/gui-runtime-matrix')
fs.mkdirSync(outDir, { recursive: true })

const modules = ['Command', 'Finance', 'Spatial', 'Anomaly', 'Graph', 'Query']
const moduleReadyHeadings = {
  Command: 'Command Center',
  Finance: 'Finance Intelligence',
  Spatial: 'Spatial Intelligence',
  Anomaly: 'Anomaly Workbench',
  Graph: 'Investigation Graph',
  Query: 'Query Layer',
}
const viewports = [320, 375, 768, 1280, 1440, 1920].map((width) => ({ width, height: width < 768 ? 844 : 900 }))
const engines = { chromium, firefox, webkit }
const results = []
let failed = false
const RASTER_FADE_HORIZON_MS = 300
const deterministicRasterTile = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64',
)

function record(entry) {
  results.push(entry)
  if (entry.status === 'FAIL') failed = true
}

async function waitForStableVisual(page, locator) {
  let previous = null
  let consecutiveMatches = 0
  for (let sample = 1; sample <= 30; sample += 1) {
    const current = await locator.screenshot({ animations: 'disabled' })
    if (previous?.equals(current)) {
      consecutiveMatches += 1
      if (consecutiveMatches >= 2) return sample
    } else {
      consecutiveMatches = 0
    }
    previous = current
    await page.waitForTimeout(100)
  }
  throw new Error('Spatial map canvas did not reach three consecutive identical visual samples')
}

async function waitForBasemapRequestQuiescence(page, externalFixtures) {
  let previous = externalFixtures.basemapTileRequests
  let consecutiveQuietSamples = 0
  for (let sample = 1; sample <= 60; sample += 1) {
    await page.waitForTimeout(100)
    const current = externalFixtures.basemapTileRequests
    if (current > 0 && current === previous) {
      consecutiveQuietSamples += 1
      if (consecutiveQuietSamples >= 5) return sample
    } else {
      consecutiveQuietSamples = 0
    }
    previous = current
  }
  throw new Error('Basemap tile requests did not become quiescent')
}

async function waitForModuleReady(page, moduleName, externalFixtures) {
  const panel = page.locator('#module-panel')
  const readyHeading = moduleReadyHeadings[moduleName]
  const loadingPlaceholder = panel.getByText(/^Loading module(?:…|\.\.\.)$/)
  let basemapQuiescenceSamples

  await panel.getByRole('heading', { name: readyHeading, exact: true }).waitFor({
    state: 'visible',
    timeout: 30000,
  })
  await loadingPlaceholder.waitFor({ state: 'hidden', timeout: 30000 })
  if (moduleName === 'Spatial') {
    await panel.getByRole('button', { name: 'Municipios rendered', exact: true }).waitFor({
      state: 'visible',
      timeout: 30000,
    })
    await page.waitForLoadState('networkidle', { timeout: 30000 })
    basemapQuiescenceSamples = await waitForBasemapRequestQuiescence(page, externalFixtures)
    await page.waitForTimeout(RASTER_FADE_HORIZON_MS)
  }
  await page.evaluate(async () => {
    await document.fonts.ready
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  })
  const visualStabilitySamples =
    moduleName === 'Spatial'
      ? await waitForStableVisual(page, panel.locator('.maplibregl-canvas'))
      : undefined

  return {
    readyHeading,
    readyHeadingVisible: await panel.getByRole('heading', { name: readyHeading, exact: true }).isVisible(),
    loadingPlaceholderVisible: await loadingPlaceholder.isVisible(),
    basemapTileRequests: externalFixtures.basemapTileRequests,
    basemapQuiescenceSamples,
    visualStabilitySamples,
  }
}

async function installDeterministicExternalFixtures(context) {
  const state = { basemapTileRequests: 0 }
  await context.route('https://tile.openstreetmap.org/**', async (route) => {
    state.basemapTileRequests += 1
    await route.fulfill({ status: 200, contentType: 'image/png', body: deterministicRasterTile })
  })
  return state
}

for (const [engineName, engine] of Object.entries(engines)) {
  const browser = await engine.launch({ headless: true })
  try {
    for (const viewport of viewports) {
      const context = await browser.newContext({ viewport, reducedMotion: 'no-preference' })
      const externalFixtures = await installDeterministicExternalFixtures(context)
      const page = await context.newPage()
      const runtimeErrors = []
      page.on('pageerror', (error) => runtimeErrors.push(`page error: ${String(error)}`))
      page.on('console', (message) => {
        if (/The above error occurred|Unhandled render error|There is no style added|feature id is required|maplibre-gl-worker/i.test(message.text())) {
          runtimeErrors.push(`console ${message.type()}: ${message.text()}`)
        }
      })

      try {
        await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 })
        await page.getByRole('tab', { name: 'Command', exact: true }).waitFor({ timeout: 30000 })

        for (const moduleName of modules) {
          const errorOffset = runtimeErrors.length
          const tab = page.getByRole('tab', { name: moduleName, exact: true })
          await tab.click()
          const readiness = await waitForModuleReady(page, moduleName, externalFixtures)
          const selected = await tab.getAttribute('aria-selected')
          const moduleErrors = runtimeErrors.slice(errorOffset)
          const layout = await page.evaluate(() => ({
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
            bodyScrollWidth: document.body.scrollWidth,
            bodyClientWidth: document.body.clientWidth,
          }))
          const horizontalOverflow =
            layout.scrollWidth > layout.clientWidth + 1 ||
            layout.bodyScrollWidth > layout.bodyClientWidth + 1
          const file = `${engineName}-${viewport.width}-${moduleName.toLowerCase()}.png`
          await page.screenshot({ path: path.join(outDir, file), fullPage: true, animations: 'disabled' })
          record({
            engine: engineName,
            viewport: viewport.width,
            surface: moduleName,
            status:
              selected === 'true' &&
              readiness.readyHeadingVisible &&
              !readiness.loadingPlaceholderVisible &&
              (moduleName !== 'Spatial' || readiness.basemapTileRequests > 0) &&
              moduleErrors.length === 0 &&
              !horizontalOverflow
                ? 'PASS'
                : 'FAIL',
            aria_selected: selected,
            ready_heading: readiness.readyHeading,
            ready_heading_visible: readiness.readyHeadingVisible,
            loading_placeholder_visible: readiness.loadingPlaceholderVisible,
            ...(moduleName === 'Spatial'
              ? {
                  basemap_tile_requests: readiness.basemapTileRequests,
                  basemap_quiescence_samples: readiness.basemapQuiescenceSamples,
                  raster_fade_horizon_ms: RASTER_FADE_HORIZON_MS,
                  visual_stability_samples: readiness.visualStabilitySamples,
                }
              : {}),
            page_errors: moduleErrors,
            horizontal_overflow: horizontalOverflow,
            layout,
            screenshot: file,
          })
        }

        const keyboardTarget = page.getByRole('tab', { name: 'Finance', exact: true })
        await keyboardTarget.focus()
        await page.keyboard.press('Enter')
        await page.waitForTimeout(50)
        const focused = await page.evaluate(() => {
          const el = document.activeElement
          if (!el || el === document.body) return null
          const style = getComputedStyle(el)
          const rect = el.getBoundingClientRect()
          return {
            tag: el.tagName,
            text: (el.textContent || '').trim().slice(0, 80),
            visible: style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0,
          }
        })
        record({
          engine: engineName,
          viewport: viewport.width,
          mode: 'keyboard-only',
          status: focused?.visible && (await keyboardTarget.getAttribute('aria-selected')) === 'true' ? 'PASS' : 'FAIL',
          focused,
          target: 'Finance tab',
          key: 'Enter',
        })

        await page.evaluate(() => { document.documentElement.style.zoom = '2' })
        const zoomLayout = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
          bodyWidth: document.body.getBoundingClientRect().width,
        }))
        record({
          engine: engineName,
          viewport: viewport.width,
          mode: 'css-200%-zoom-surrogate',
          status: Number.isFinite(zoomLayout.scrollWidth) && zoomLayout.scrollWidth > 0 ? 'PASS' : 'FAIL',
          note: 'CSS zoom stress only; not credited as native browser 200% zoom certification.',
          layout: zoomLayout,
        })
      } catch (error) {
        record({ engine: engineName, viewport: viewport.width, status: 'FAIL', error: String(error), runtime_errors: runtimeErrors })
      } finally {
        await context.close()
      }
    }

    const reduced = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' })
    await installDeterministicExternalFixtures(reduced)
    const reducedPage = await reduced.newPage()
    try {
      await reducedPage.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 })
      const matches = await reducedPage.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)
      record({ engine: engineName, viewport: 1280, mode: 'reduced-motion', status: matches ? 'PASS' : 'FAIL' })
    } catch (error) {
      record({ engine: engineName, viewport: 1280, mode: 'reduced-motion', status: 'FAIL', error: String(error) })
    } finally {
      await reduced.close()
    }
  } finally {
    await browser.close()
  }
}

const densityBrowser = await chromium.launch({ headless: true })
try {
  const context = await densityBrowser.newContext({ viewport: { width: 1280, height: 900 } })
  const externalFixtures = await installDeterministicExternalFixtures(context)
  const page = await context.newPage()
  const pageErrors = []
  const spatialRuntimeErrors = []
  let attempts = 0
  let tileJsonAttempts = 0
  page.on('pageerror', (error) => pageErrors.push(String(error)))
  page.on('console', (message) => {
    if (/feature id is required|removeFeatureState|setFeatureState|maplibre-gl-worker|no style added/i.test(message.text())) {
      spatialRuntimeErrors.push(message.text())
    }
  })
  await page.route('**/tiles/municipios**', async (route) => {
    const requestUrl = new URL(route.request().url())
    if (requestUrl.pathname !== '/tiles/municipios') {
      await route.fulfill({ status: 204, body: '' })
      return
    }
    tileJsonAttempts += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        minzoom: 0,
        maxzoom: 14,
        tiles: [`${BASE_URL}/tiles/municipios/{z}/{x}/{y}`],
        vector_layers: [{ id: 'municipios' }],
      }),
    })
  })
  await page.route('**/geo/municipios/density**', async (route) => {
    attempts += 1
    if (attempts === 1) {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'matrix retry probe' }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        by_geoid: { '72127': 2 },
        matched_count: 2,
        unmatched: 1,
        total_features: 3,
        scope: { identity_effect: 'NONE', state: 'CANDIDATE_NOT_IDENTITY' },
      }),
    })
  })

  try {
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 })
    await page.getByRole('tab', { name: 'Command', exact: true }).waitFor({ timeout: 30000 })
    await page.getByRole('tab', { name: 'Spatial', exact: true }).click()
    await page.getByRole('button', { name: /Municipios rendered/ }).waitFor({ timeout: 30000 })
    const densityButton = page.getByRole('button', { name: /Gazetteer density/ })
    await densityButton.waitFor({ timeout: 30000 })
    await densityButton.click()
    await page.getByRole('alert').filter({ hasText: 'Density unavailable' }).waitFor()
    await page.getByRole('button', { name: 'retry', exact: true }).click()
    await page.getByRole('status').filter({ hasText: '2 matched · 1 unresolved · 3 total' }).waitFor()
    await densityButton.click()
    await page.waitForTimeout(250)
    record({
      engine: 'chromium',
      viewport: 1280,
      mode: 'spatial-density-retry-and-cleanup',
      status: externalFixtures.basemapTileRequests > 0 && tileJsonAttempts > 0 && attempts === 2 && pageErrors.length === 0 && spatialRuntimeErrors.length === 0 ? 'PASS' : 'FAIL',
      basemap_tile_requests: externalFixtures.basemapTileRequests,
      tilejson_attempts: tileJsonAttempts,
      attempts,
      page_errors: pageErrors,
      spatial_runtime_errors: spatialRuntimeErrors,
    })
  } catch (error) {
    record({
      engine: 'chromium',
      viewport: 1280,
      mode: 'spatial-density-retry-and-cleanup',
      status: 'FAIL',
      error: String(error),
      basemap_tile_requests: externalFixtures.basemapTileRequests,
      tilejson_attempts: tileJsonAttempts,
      attempts,
      page_errors: pageErrors,
      spatial_runtime_errors: spatialRuntimeErrors,
    })
  } finally {
    await context.close()
  }
} finally {
  await densityBrowser.close()
}

const summary = {
  schema_version: '1.1',
  app: 'spiderweb-pr',
  architecture: 'single-workbench-six-modules',
  engines: Object.keys(engines),
  viewports: viewports.map((v) => v.width),
  expected_surface_cells: Object.keys(engines).length * viewports.length * modules.length,
  observed_surface_cells: results.filter((r) => r.surface).length,
  failures: results.filter((r) => r.status === 'FAIL').length,
  native_200_percent_zoom_certified: false,
  results,
}
fs.writeFileSync(path.join(outDir, 'summary.json'), JSON.stringify(summary, null, 2) + '\n')
console.log(JSON.stringify({ expected_surface_cells: summary.expected_surface_cells, observed_surface_cells: summary.observed_surface_cells, failures: summary.failures }, null, 2))
process.exit(failed ? 1 : 0)
