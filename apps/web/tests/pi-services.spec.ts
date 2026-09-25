import { test, expect } from "@playwright/test";
import { signIn } from "./helpers";

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
