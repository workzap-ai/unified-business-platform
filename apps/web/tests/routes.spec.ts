import { test, expect } from "@playwright/test";
import registry from "../src/features/navigation/registry.generated.json";
import type { NavDefinition } from "../src/features/navigation/types";
import { signIn } from "./helpers";

// Every registered route (sidebar, module tabs, PI sub-navigation) must render a real page:
// no 404, no error boundary, a heading present. Extra deep routes are listed explicitly.
const routes = [
  ...new Set([
    ...(registry as NavDefinition[]).map((d) => d.route),
    "/customers/new",
    "/catalog/products/new",
    "/quotes/new",
    "/orders/new",
    "/billing/invoices/new",
    "/hr/employees/new",
    "/pi/agents/new",
    "/pi/whatsapp/status",
    "/pi/whatsapp/events",
    "/pi/knowledge/sources",
    "/pi/knowledge/documents",
    "/pi/knowledge/ingestion",
    "/pi/handoffs/open",
    "/pi/handoffs/in-progress",
    "/pi/analytics/conversations",
    "/pi/analytics/fallbacks",
    "/pi/settings/business-hours",
    "/pi/settings/provider-configuration",
    "/settings/roles/new",
    "/account",
  ]),
];

test.describe.configure({ mode: "serial" });

test("every registered route renders a page", async ({ page }) => {
  test.setTimeout(10 * 60_000);
  const failures: string[] = [];
  page.on("pageerror", (e) => failures.push(`pageerror: ${e.message}`));
  await signIn(page);
  for (const route of routes) {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    const notFound = await page
      .getByRole("heading", { name: "Page not found" })
      .count();
    const crashed = await page
      .getByRole("heading", { name: "Something went wrong" })
      .count();
    const heading = await page.locator("main h1").count();
    if (notFound || crashed || !heading)
      failures.push(
        `${route}: ${notFound ? "404" : crashed ? "error boundary" : "no h1"}`,
      );
  }
  expect(failures).toEqual([]);
});
