import { expect, test } from "@playwright/test";

import { mockApi, OWNER, VIEWER } from "./support";

const MANAGER = [...OWNER, "pi.campaigns.read", "pi.campaigns.manage"];
const SENT = {
  id: "c1",
  name: "Eid collection",
  template_name: "eid_offer",
  template_language: "en",
  audience_tag: null,
  status: "completed",
  scheduled_at: "2026-09-30T05:00:00Z",
  started_at: "2026-09-30T05:00:00Z",
  finished_at: "2026-09-30T05:01:00Z",
  max_recipients: 500,
  daily_limit: 200,
  quiet_start: 21,
  quiet_end: 9,
  results: {
    recipients: 2,
    waiting: 0,
    sent: 1,
    delivered: 1,
    read: 1,
    failed: 0,
    skipped: 1,
    replied: 1,
    skipped_reasons: { OPTED_OUT: 1 },
  },
};

test("campaign results and a new draft", async ({ page }) => {
  await mockApi(page, MANAGER, {
    "GET /pi/campaigns": [SENT],
    "GET /pi/campaigns/audience": {
      count: 12,
      plan_allows: true,
      whatsapp_connected: true,
    },
  });
  await page.goto("/customers/campaigns");
  await expect(
    page.getByRole("heading", { name: "Eid collection" }),
  ).toBeVisible();
  await expect(page.getByText("1 said stop")).toBeVisible();
  await expect(
    page.getByText("12 customers agreed to receive messages."),
  ).toBeVisible();
  const saved = page.waitForRequest(
    (r) => r.url().endsWith("/pi/campaigns") && r.method() === "POST",
  );
  await page.getByLabel("Campaign name").fill("Winter sale");
  await page.getByLabel("WhatsApp template name").fill("winter_sale");
  await page.getByRole("button", { name: "Save draft" }).click();
  const body = (await saved).postDataJSON();
  expect(body).toMatchObject({
    name: "Winter sale",
    template_name: "winter_sale",
    template_language: "en",
    quiet_start: 21,
    quiet_end: 9,
  });
});

test("viewers see results but cannot create or cancel", async ({ page }) => {
  await mockApi(page, [...VIEWER, "pi.campaigns.read"], {
    "GET /pi/campaigns": [{ ...SENT, status: "sending" }],
  });
  await page.goto("/customers/campaigns");
  await expect(
    page.getByRole("heading", { name: "Eid collection" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Save draft" })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Cancel campaign" }),
  ).toHaveCount(0);
});

test("campaigns fit a phone screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await mockApi(page, MANAGER, {
    "GET /pi/campaigns": [SENT],
    "GET /pi/campaigns/audience": {
      count: 3,
      plan_allows: false,
      whatsapp_connected: true,
    },
  });
  await page.goto("/customers/campaigns");
  await expect(
    page.getByText("Campaigns are included in the Growth"),
  ).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});
