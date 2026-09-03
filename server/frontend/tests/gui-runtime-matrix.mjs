import fs from 'node:fs'
import path from 'node:path'
import { chromium, firefox, webkit } from 'playwright'

const BASE_URL = process.env.GUI_BASE_URL || 'http://127.0.0.1:5173'
const outDir = path.resolve(process.env.GUI_ARTIFACT_DIR || 'artifacts/gui-runtime-matrix')
fs.mkdirSync(outDir, { recursive: true })

const modules = ['Command', 'Finance', 'Spatial', 'Anomaly', 'Graph', 'Query']
const viewports = [320, 375, 768, 1280, 1440, 1920].map((width) => ({ width, height: width < 768 ? 844 : 900 }))
const engines = { chromium, firefox, webkit }
const results = []
let failed = false

function record(entry) {
  results.push(entry)
  if (entry.status === 'FAIL') failed = true
}

for (const [engineName, engine] of Object.entries(engines)) {
  const browser = await engine.launch({ headless: true })
  try {
    for (const viewport of viewports) {
      const context = await browser.newContext({ viewport, reducedMotion: 'no-preference' })
      const page = await context.newPage()
      const pageErrors = []
      page.on('pageerror', (error) => pageErrors.push(String(error)))

      try {
        await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 })
        await page.getByRole('tab', { name: 'Command', exact: true }).waitFor({ timeout: 30000 })

        for (const moduleName of modules) {
          const errorOffset = pageErrors.length
          const tab = page.getByRole('tab', { name: moduleName, exact: true })
          await tab.click()
          await page.waitForTimeout(150)
          const selected = await tab.getAttribute('aria-selected')
          const moduleErrors = pageErrors.slice(errorOffset)
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
          await page.screenshot({ path: path.join(outDir, file), fullPage: true })
          record({
            engine: engineName,
            viewport: viewport.width,
            surface: moduleName,
            status: selected === 'true' && moduleErrors.length === 0 && !horizontalOverflow ? 'PASS' : 'FAIL',
            aria_selected: selected,
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
        record({ engine: engineName, viewport: viewport.width, status: 'FAIL', error: String(error), page_errors: pageErrors })
      } finally {
        await context.close()
      }
    }

    const reduced = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' })
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
