import { test, expect } from "@playwright/test";
import { signIn, mainLabels } from "./helpers";

test("service workspace hides inventory and creates an untracked offering", async ({
  page,
}) => {
  await signIn(page);
  await page.getByRole("button", { name: /Workspace: Northwind/ }).click();
  await page.getByRole("button", { name: "Brightline Studio" }).click();
  await expect.poll(() => mainLabels(page)).not.toContain("Inventory");
  await page.goto("/catalog/products/new");
  await expect(page.getByLabel("Offering type")).toHaveValue("service");
  await expect(page.locator("#variant-0-track")).toBeDisabled();
  await page.getByLabel("Offering name").fill("Website and AI chatbot");
  await page.locator("#variant-0-sku").fill("WEB-AI-TEST");
  await page.locator("#variant-0-name").fill("Implementation package");
  await page.locator("#variant-0-price").fill("2500.00");
  await page.getByRole("button", { name: "Create offering" }).click();
  await expect(
    page.getByRole("heading", { name: "Website and AI chatbot", exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/SERVICE ·/)).toBeVisible();
});

test("service creation remains usable at required viewport widths", async ({
  page,
}) => {
  await signIn(page, "/catalog/products/new");
  for (const width of [390, 430, 768, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(
      page.getByRole("heading", { name: "Add offering" }),
    ).toBeVisible();
    await expect(page.getByLabel("Offering type")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBeTruthy();
  }
});
