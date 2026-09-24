// Usage: node shot.mjs <base> <outdir> <width> <path1> [path2 ...]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const [base, out, width, ...paths] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: Number(width), height: 900 } });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text()}`); });
await page.goto(`${base}/login`);
await page.getByRole("button", { name: "Sign in" }).click();
await page.waitForURL(`${base}/`);
for (const p of paths) {
  await page.goto(`${base}${p}`);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(900);
  const name = (p === "/" ? "overview" : p.replace(/[\/?=&]+/g, "_").replace(/^_/, "")) + `-${width}.png`;
  await page.screenshot({ path: `${out}/${name}`, fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  console.log(`${p} -> ${name}${overflow ? " [HORIZONTAL OVERFLOW]" : ""}`);
}
console.log(errors.length ? errors.slice(0, 15).join("\n") : "no console errors");
await browser.close();
