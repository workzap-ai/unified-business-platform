import { test, expect, type Page } from "@playwright/test";
import { signIn } from "./helpers";

// Runs against the demo-mode server: every connection, event and key is sample data.

const DIRECTORY = "/settings/integrations";

async function noHorizontalOverflow(page: Page) {
  return page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth + 1,
  );
}

test("directory groups integrations by category and planned ones can't be connected", async ({
  page,
}) => {
  await signIn(page, DIRECTORY);
  await expect(
    page.getByRole("heading", { level: 1, name: "Integrations" }),
  ).toBeVisible();
  for (const category of ["Messaging", "Email", "Automation", "Calendar"]) {
    await expect(
      page.getByRole("heading", { level: 3, name: category, exact: true }),
    ).toBeVisible();
  }
  const planned = page.locator('[data-integration="google_calendar"]');
  await expect(planned).toContainText("Planned");
  await expect(planned).toContainText("can't be connected yet");
  await expect(planned.getByRole("link", { name: /Connect/ })).toHaveCount(0);
  // Seeded connections for this workspace are listed with their real status.
  await expect(
    page.getByRole("link", { name: "Northwind WhatsApp line" }),
  ).toBeVisible();

  await page.goto(`${DIRECTORY}/google_calendar?connect=1`);
  await expect(
    page.getByText("Planned integration", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect" })).toBeDisabled();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("connect a generic webhook: secret is write-only, test, and confirmed disconnect", async ({
  page,
}) => {
  const secret = "sup3r-Secret-value-XYZ9";
  await signIn(page, DIRECTORY);
  await page.getByRole("link", { name: "Connect Generic webhook" }).click();
  const dialog = page.getByRole("dialog", { name: "Connect Generic webhook" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Connection name").fill("QA automation hook");
  // Client-side SSRF pre-check.
  await dialog.getByLabel("Endpoint URL").fill("https://127.0.0.1/hook");
  await dialog.getByLabel("Signing secret").fill(secret);
  await dialog
    .getByRole("button", { name: "Save and test connection" })
    .click();
  await expect(dialog.getByText(/Private, loopback/)).toBeVisible();
  await dialog.getByLabel("Endpoint URL").fill("https://hooks.example.com/qa");
  await dialog
    .getByRole("button", { name: "Save and test connection" })
    .click();

  await expect(page).toHaveURL(/\/settings\/integrations\/connections\//);
  await expect(
    page.getByRole("heading", { level: 1, name: "QA automation hook" }),
  ).toBeVisible();
  await expect(page.getByTestId("credentials")).toContainText("set • …XYZ9");
  expect(await page.content()).not.toContain(secret);

  await page.getByRole("button", { name: "Test connection" }).click();
  const result = page.getByTestId("test-result");
  await expect(result).toContainText("Test passed");
  await expect(result).toContainText("Sample result");
  await expect(result).toContainText(/Latency \d+ ms/);

  await page.getByRole("button", { name: "Disconnect" }).click();
  const confirm = page.getByRole("dialog", {
    name: "Disconnect QA automation hook?",
  });
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: "Cancel" }).click();
  await expect(confirm).toHaveCount(0);
  await expect(page.getByText("Credentials were revoked")).toHaveCount(0);

  await page.getByRole("button", { name: "Disconnect" }).click();
  await page
    .getByRole("dialog", { name: "Disconnect QA automation hook?" })
    .getByRole("button", { name: "Disconnect" })
    .click();
  await expect(
    page.getByText(/Credentials were revoked and nothing/),
  ).toBeVisible();
  await expect(page.getByTestId("credentials")).toContainText("Not set");
  expect(await page.content()).not.toContain(secret);
});

test("testing a degraded connection reports the failure honestly", async ({
  page,
}) => {
  await signIn(page, DIRECTORY);
  await page.getByRole("link", { name: "Northwind WhatsApp line" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Northwind WhatsApp line" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Test connection" }).click();
  const result = page.getByTestId("test-result");
  await expect(result).toContainText("Test failed");
  await expect(result).toContainText("rate limiting");
  await expect(result).not.toContainText("Connected");
});

test("webhook signing secret is shown once and gone after closing", async ({
  page,
}) => {
  await signIn(page, `${DIRECTORY}/webhooks`);
  await page.getByRole("button", { name: "New subscription" }).click();
  const dialog = page.getByRole("dialog", { name: "New webhook subscription" });
  await dialog.getByLabel("Name").fill("QA receiver");
  await dialog
    .getByLabel("Endpoint URL")
    .fill("https://receiver.example.com/in");
  await dialog.getByRole("button", { name: "Create subscription" }).click();
  await expect(
    dialog.getByText("Choose at least one event type"),
  ).toBeVisible();
  await dialog.getByLabel(/order\.confirmed/).check();
  await dialog.getByRole("button", { name: "Create subscription" }).click();

  const revealed = page.getByTestId("revealed-secret");
  await expect(revealed).toHaveValue(/^whsec_/);
  const secret = await revealed.inputValue();
  await expect(page.getByText("You won't see this again")).toBeVisible();
  await page.getByRole("button", { name: "I've stored it safely" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByTestId("revealed-secret")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "QA receiver", exact: true }),
  ).toBeVisible();
  expect(await page.content()).not.toContain(secret);
});

test("API key can be created (secret once) and revoked", async ({ page }) => {
  await signIn(page, `${DIRECTORY}/api-keys`);
  await page.getByRole("button", { name: "Create API key" }).click();
  const dialog = page.getByRole("dialog", { name: "Create API key" });
  await dialog.getByLabel("Name").fill("QA script");
  await dialog.getByLabel("View customers").check();
  await dialog.getByRole("button", { name: "Create key" }).click();
  const revealed = page.getByTestId("revealed-secret");
  await expect(revealed).toHaveValue(/^pk_live_[a-z0-9]{6}_/);
  const secret = await revealed.inputValue();
  await page.getByRole("button", { name: "I've stored it safely" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(await page.content()).not.toContain(secret);

  const row = page.locator("tr", { hasText: "QA script" });
  await expect(row).toContainText("Active");
  await row.getByRole("button", { name: "Revoke QA script" }).click();
  await page
    .getByRole("dialog", { name: "Revoke QA script?" })
    .getByRole("button", { name: "Revoke key" })
    .click();
  await expect(row).toContainText("Revoked");
  await expect(row.getByRole("button", { name: /Revoke/ })).toHaveCount(0);
});

test("failures can be retried where allowed", async ({ page }) => {
  await signIn(page, `${DIRECTORY}/failures`);
  const jobRetry = page.getByRole("button", { name: "Retry sync job" });
  await expect(jobRetry).toHaveCount(1);
  await jobRetry.click();
  await expect(page.getByText(/Retry queued: pending/)).toBeVisible();
  await expect(jobRetry).toHaveCount(0);
  // Unverified events are never offered for replay.
  await page.goto(`${DIRECTORY}/events?status=ignored`);
  const replay = page.getByRole("button", { name: /Replay message\.received/ });
  await expect(replay).toBeDisabled();
});

test("sync job actions follow the state machine", async ({ page }) => {
  await signIn(page, `${DIRECTORY}/jobs?status=paused`);
  await page
    .getByRole("button", { name: /Actions for products incremental/ })
    .click();
  await expect(page.getByRole("menuitem", { name: /Pause/ })).toBeDisabled();
  await expect(page.getByRole("menuitem", { name: /Retry/ })).toBeDisabled();
  await page.getByRole("menuitem", { name: /Resume/ }).click();
  await expect(page.getByText(/sync is now running/)).toBeVisible();
});

test("a new environment starts empty", async ({ page }) => {
  await signIn(page);
  await page.getByRole("button", { name: /Environment: Production/ }).click();
  await page.getByRole("button", { name: /Staging/ }).click();
  await expect(
    page.getByRole("button", { name: /Environment: Staging/ }),
  ).toBeVisible();
  await page.goto(DIRECTORY);
  await expect(
    page.getByText("No connections in this environment yet"),
  ).toBeVisible();
});

test("mobile 390px has no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, DIRECTORY);
  await expect(page.locator('[data-category="messaging"]')).toBeVisible();
  expect(await noHorizontalOverflow(page)).toBeTruthy();
  await page.goto(`${DIRECTORY}/connections/con-nw-wa`);
  await expect(
    page.getByRole("heading", { level: 1, name: "Northwind WhatsApp line" }),
  ).toBeVisible();
  expect(await noHorizontalOverflow(page)).toBeTruthy();
});

test("roles without integration access don't see Integrations", async ({
  page,
}) => {
  await signIn(page);
  const admin = page.getByRole("navigation", { name: "Administration" });
  await expect(admin.getByRole("link", { name: "Integrations" })).toBeVisible();
  await page.getByRole("button", { name: /Account menu/ }).click();
  await page.getByRole("menuitem", { name: "View as role" }).focus();
  await page.keyboard.press("ArrowRight");
  await page.getByRole("menuitem", { name: "Viewer", exact: true }).click();
  await expect(page.getByRole("link", { name: "Integrations" })).toHaveCount(0);
  await page.goto(DIRECTORY);
  await expect(
    page.getByRole("heading", { name: /have access to integrations/ }),
  ).toBeVisible();
});
