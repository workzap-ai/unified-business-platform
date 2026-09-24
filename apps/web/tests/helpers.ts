import { expect, type Page } from "@playwright/test";

export const DEFAULT_MAIN = [
  "Overview",
  "Customers / CRM",
  "Catalog",
  "PI",
  "Inventory",
  "Sales",
  "Quotes",
  "Orders",
  "Billing",
  "Finance",
  "HR",
  "Reports",
];

/** Sign in to the sample-data workspace (demo data mode; no API involved). */
export async function signIn(page: Page, path = "/") {
  await page.goto("/login");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/");
  if (path !== "/") await page.goto(path);
}

export function primaryNav(page: Page) {
  return page.getByRole("navigation", { name: "Primary" });
}

export async function mainLabels(page: Page) {
  const nav = primaryNav(page);
  await expect(nav.locator("a[data-nav-key]").first()).toBeVisible();
  return nav.locator("a[data-nav-key]").evaluateAll((links) =>
    links.map((a) => (a.querySelector("span.truncate")?.textContent ?? "").trim()),
  );
}
