import { test, expect } from "@playwright/test";
import { DEFAULT_MAIN, mainLabels, primaryNav, signIn } from "./helpers";

// Each test runs in a fresh browser context, so sample-data state starts clean.

test("unauthenticated visitors are sent to sign-in with a safe return path", async ({
  page,
}) => {
  await page.goto("/orders");
  await expect(page).toHaveURL(/\/login\?next=%2Forders/);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/orders$/);
});

test("sidebar renders the default order with PI as a top-level product", async ({
  page,
}) => {
  await signIn(page);
  expect(await mainLabels(page)).toEqual(DEFAULT_MAIN);
  await expect(
    page
      .getByRole("navigation", { name: "Administration" })
      .getByRole("link", { name: "Audit Logs" }),
  ).toBeVisible();
  await expect(page.getByText("Sample data", { exact: true })).toBeVisible();
});

test("sidebar order can be changed by keyboard, persists across reload, and resets", async ({
  page,
}) => {
  await signIn(page);
  await page.getByRole("button", { name: "Customize sidebar order" }).click();
  // Move PI up twice using the accessible move buttons (keyboard alternative to dragging).
  await page.getByRole("button", { name: "Move PI up" }).click();
  await expect(page.getByText("Sidebar order saved")).toBeVisible();
  await page.getByRole("button", { name: "Move PI up" }).click();
  await page.getByRole("button", { name: "Done" }).click();
  const expected = [
    "Overview",
    "PI",
    "Customers / CRM",
    "Catalog",
    ...DEFAULT_MAIN.slice(4),
  ];
  await expect.poll(() => mainLabels(page)).toEqual(expected);
  await page.reload();
  await expect.poll(() => mainLabels(page)).toEqual(expected);

  await page.getByRole("button", { name: "Customize sidebar order" }).click();
  await page.getByRole("button", { name: "Reset" }).click();
  await page.getByRole("button", { name: "Done" }).click();
  await expect.poll(() => mainLabels(page)).toEqual(DEFAULT_MAIN);
});

test("sidebar supports drag and drop with the pointer", async ({ page }) => {
  await signIn(page);
  await page.getByRole("button", { name: "Customize sidebar order" }).click();
  const handle = page.getByRole("button", { name: "Drag Reports" });
  const target = page.locator('[data-sortable-key="overview"]');
  const from = await handle.boundingBox();
  const to = await target.boundingBox();
  if (!from || !to) throw new Error("Missing drag geometry");
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(from.x + 4, from.y - 10, { steps: 4 });
  await page.mouse.move(to.x + 20, to.y + 2, { steps: 12 });
  await page.mouse.up();
  await page.getByRole("button", { name: "Done" }).click();
  await expect.poll(async () => (await mainLabels(page))[0]).toBe("Reports");
});

test("permissions shape navigation (viewing as Support)", async ({ page }) => {
  await signIn(page);
  await page.getByRole("button", { name: /Account menu/ }).click();
  // Keyboard path through the submenu (also checks the menu is keyboard-operable).
  await page.getByRole("menuitem", { name: "View as role" }).focus();
  await page.keyboard.press("ArrowRight");
  const support = page.getByRole("menuitem", { name: "Support", exact: true });
  await expect(support).toBeVisible();
  await support.focus();
  await page.keyboard.press("Enter");
  await expect
    .poll(() => mainLabels(page))
    .toEqual([
      "Overview",
      "Customers / CRM",
      "Catalog",
      "PI",
      "Inventory",
      "Orders",
    ]);
  await page.goto("/finance");
  await expect(
    page.getByRole("heading", { name: /have access to/ }),
  ).toBeVisible();
});

test("PI disappears in an environment where the product is not enabled", async ({
  page,
}) => {
  await signIn(page);
  await page.getByRole("button", { name: /Environment: Production/ }).click();
  await page.getByRole("button", { name: /Staging/ }).click();
  await expect(
    page.getByRole("button", { name: /Environment: Staging/ }),
  ).toBeVisible();
  await expect
    .poll(() => mainLabels(page))
    .toEqual(DEFAULT_MAIN.filter((l) => l !== "PI"));
});

test("mobile uses a drawer with the same registry-driven navigation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page);
  await page.getByRole("button", { name: "Open navigation" }).click();
  expect(await mainLabels(page)).toEqual(DEFAULT_MAIN);
  await primaryNav(page)
    .getByRole("link", { name: /Quotes/ })
    .click();
  await expect(page).toHaveURL(/\/quotes$/);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBeTruthy();
});

test("command menu finds pages from the same registry", async ({ page }) => {
  await signIn(page);
  await page.keyboard.press("Control+k");
  const input = page.getByPlaceholder("Search pages, records and actions…");
  await input.fill("handoffs");
  await page.getByRole("option", { name: /PI \/ Handoffs/ }).click();
  await expect(page).toHaveURL(/\/pi\/handoffs$/);
});

test("switching workspace shows that workspace's own data", async ({
  page,
}) => {
  await signIn(page);
  await page.getByRole("button", { name: /Workspace: Northwind/ }).click();
  await page.getByRole("button", { name: "Brightline Studio" }).click();
  await expect(
    page.getByRole("button", { name: /Workspace: Brightline Studio/ }),
  ).toBeVisible();
  await page.goto("/customers");
  await expect(page.getByText("Northwind", { exact: false })).toHaveCount(0);
});
