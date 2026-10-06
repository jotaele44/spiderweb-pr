import { chromium } from "playwright";
import fs from "node:fs/promises";

const base = process.env.RECOVERY_PREVIEW_URL || "http://127.0.0.1:4173";
const cases = [
  { name: "desktop-1440", width: 1440, height: 900 },
  { name: "iphone-393", width: 393, height: 852 },
  { name: "iphone-430", width: 430, height: 932 },
];

const browser = await chromium.launch({ headless: true });
const results = [];
let failed = false;

for (const item of cases) {
  const context = await browser.newContext({ viewport: { width: item.width, height: item.height } });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", msg => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
  const response = await page.goto(base + "/spatial-analysis", { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(500);

  const body = await page.locator("body").innerText();
  const metrics = await page.evaluate(() => ({
    href: location.href,
    documentClientWidth: document.documentElement.clientWidth,
    documentScrollWidth: document.documentElement.scrollWidth,
    bodyClientWidth: document.body.clientWidth,
    bodyScrollWidth: document.body.scrollWidth,
  }));

  const required = [
    "Spatial analysis workbench",
    "Dataset intake",
    "MANIFEST → DATASET → PREFLIGHT → ANALYSIS → RECEIPT",
    "Stage spatial source files",
    "MANIFEST_AUDIT",
    "PREFLIGHT",
  ];
  const missing = required.filter(text => !body.includes(text));
  const horizontalOverflow = metrics.documentScrollWidth > metrics.documentClientWidth + 1 ||
    metrics.bodyScrollWidth > metrics.bodyClientWidth + 1;
  const routeOk = new URL(page.url()).pathname === "/spatial-analysis";
  const ok = Boolean(response?.ok()) && routeOk && missing.length === 0 && !horizontalOverflow;

  await page.screenshot({ path: `rendered-${item.name}.png`, fullPage: true });
  results.push({
    viewport: item,
    status: response?.status() ?? null,
    routeOk,
    finalUrl: page.url(),
    missing,
    horizontalOverflow,
    metrics,
    consoleErrors,
    ok,
  });
  if (!ok) failed = true;
  await context.close();
}

await browser.close();
await fs.writeFile("rendered-qa.json", JSON.stringify({ schemaVersion: "spiderweb.rendered_qa.v1", results }, null, 2));
console.log(JSON.stringify(results, null, 2));
if (failed) process.exit(1);
