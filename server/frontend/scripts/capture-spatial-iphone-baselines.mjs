import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium } from "playwright";

const baseUrl = process.env.SPIDERWEB_VISUAL_BASE_URL ?? "http://127.0.0.1:5173";
const outputDir = resolve("src/test/visual-baselines");
const executablePath = process.env.SPIDERWEB_CHROMIUM_PATH || undefined;

const profiles = [
  { name: "iphone-portrait", width: 390, height: 844 },
  { name: "iphone-landscape", width: 844, height: 390 },
];

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ executablePath });

try {
  for (const profile of profiles) {
    const page = await browser.newPage({
      viewport: { width: profile.width, height: profile.height },
      deviceScaleFactor: 3,
      isMobile: true,
      hasTouch: true,
    });
    await page.addInitScript(() => {
      localStorage.setItem("priis_spatial_mode", "cesium");
      localStorage.setItem("priis_left_collapsed", "true");
      localStorage.setItem("priis_right_collapsed", "true");
    });
    await page.goto(baseUrl, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "Spatial" }).click();
    await page.getByRole("button", { name: "Recenter map on Puerto Rico" }).waitFor();
    await page.waitForTimeout(1_500);

    const overlay = page.locator("vite-error-overlay");
    if (await overlay.count()) throw new Error(`Vite error overlay in ${profile.name}`);
    if ((await page.locator("body").innerText()).trim().length === 0) {
      throw new Error(`Blank page in ${profile.name}`);
    }

    await page.screenshot({
      path: resolve(outputDir, `${profile.name}.png`),
      animations: "disabled",
    });
    await page.close();
  }
} finally {
  await browser.close();
}
