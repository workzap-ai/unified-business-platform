import { test, expect } from "@playwright/test";
import { signIn } from "./helpers";

test("configure business events on a connected webhook without inventing delivery history", async ({
  page,
}) => {
  await signIn(page, "/settings/integrations");
  await page.getByRole("link", { name: "Connect Generic webhook" }).click();
  const dialog = page.getByRole("dialog", { name: "Connect Generic webhook" });
  await dialog.getByLabel("Connection name").fill("Business workflow QA");
  await dialog
    .getByLabel("Endpoint URL")
    .fill("https://hooks.example.com/business");
  await dialog
    .getByLabel("Signing secret")
    .fill("workflow-qa-secret-123456789");
  await dialog
    .getByRole("button", { name: "Save and test connection" })
    .click();
  await expect(
    page.getByText("Use this integration", { exact: true }),
  ).toBeVisible();
  const enabled = page.getByLabel("Automatically deliver selected events");
  const event = page.getByLabel("A customer record was created", {
    exact: true,
  });
  await expect(enabled).not.toBeChecked();
  await event.check();
  await enabled.check();
  await page.getByRole("button", { name: "Save workflow" }).click();
  await expect(page.getByText("Workflow settings saved")).toBeVisible();
  await expect(enabled).toBeChecked();
  await expect(event).toBeChecked();
  await expect(
    page.getByRole("button", { name: "Save workflow" }),
  ).toBeDisabled();
  await expect(
    page.getByText(
      "No workflow activity yet. Connection tests are shown separately.",
    ),
  ).toBeVisible();
  await enabled.uncheck();
  await page.getByRole("button", { name: "Save workflow" }).click();
  await expect(enabled).not.toBeChecked();
});

test("disabled email connection explains usage and cannot enable automatic delivery", async ({
  page,
}) => {
  await signIn(page, "/settings/integrations");
  await page
    .getByRole("link", { name: "Transactional email", exact: true })
    .click();
  await expect(page.getByText("Invoice email", { exact: true })).toBeVisible();
  await expect(
    page.getByLabel("Automatically deliver selected events"),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Save workflow" }),
  ).toBeDisabled();
  // Multiple addresses remain editable without losing delimiters while typing.
  await page
    .getByLabel("Email recipients")
    .pressSequentially("one@example.com, two@example.com");
  await expect(page.getByLabel("Email recipients")).toHaveValue(
    "one@example.com, two@example.com",
  );
});
