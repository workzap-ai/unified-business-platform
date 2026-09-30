import { test, expect } from "@playwright/test";
import { signIn } from "./helpers";

test("PI permissions display current access without unsupported editing", async ({
  page,
}) => {
  await signIn(page, "/pi/settings/permissions");
  await expect(
    page.getByRole("table", { name: "Current PI access" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Roles & Permissions", exact: true }).last(),
  ).toBeVisible();
  await expect(page.locator("main").getByRole("switch")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Save changes", exact: true }),
  ).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
  const region = page.getByRole("region", {
    name: "PI permissions",
    exact: true,
  });
  await region.focus();
  await expect(region).toBeFocused();
});

test("PI knowledge overview contains long document titles on mobile", async ({
  page,
}) => {
  await signIn(page, "/pi/knowledge/documents");
  await page
    .getByRole("button", { name: "Add document", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog", { name: "Add document" });
  const title =
    "WorkZap product and onboarding overview with detailed retail integration and operational guidance";
  await dialog.getByRole("textbox", { name: "Title", exact: true }).fill(title);
  await dialog
    .getByRole("textbox", { name: "Content", exact: true })
    .fill(
      "A test knowledge document with a long title for mobile layout verification.",
    );
  await dialog
    .getByRole("button", { name: "Add document", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
  await page
    .getByRole("navigation", { name: "Knowledge sections" })
    .getByRole("link", { name: "Overview", exact: true })
    .click();
  await expect(page.getByText(title, { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
});

test("PI service mode and reminder settings are editable", async ({ page }) => {
  await signIn(page, "/pi/settings/response-rules");
  await expect(
    page.getByLabel("Service enquiries", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Service enquiries", { exact: true })
    .selectOption("service");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByText("Settings saved", { exact: true })).toBeVisible();
  await page.goto("/pi/settings/whatsapp-configuration");
  await expect(
    page.getByRole("heading", { name: "Follow-up reminders", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Days without a reply", { exact: true }),
  ).toHaveValue("7");
  await expect(page.getByText("Videos", { exact: true })).toBeVisible();
  await page
    .getByLabel("Customer language code", { exact: true })
    .fill("roman_ur");
  await page
    .getByLabel("Approved reminder template name", { exact: true })
    .fill("service_followup_urdu");
  await page
    .getByLabel("Meta template language code", { exact: true })
    .fill("ur");
  await page.getByRole("button", { name: "Add template", exact: true }).click();
  await expect(
    page.getByText("roman_ur: service_followup_urdu (ur)", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByText("Settings saved", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
});
