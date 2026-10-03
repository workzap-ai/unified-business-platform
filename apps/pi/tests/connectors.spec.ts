import { expect, test } from "@playwright/test";

import { mockApi, noHorizontalOverflow, OWNER } from "./support";

// Tools → "Your accounts" (Google Calendar, Shopify). API doubles only: this checks the
// states, permissions and redirect handling of the screen, not a live provider.

const account = {
  name: "Brightline Studio",
  business_category: "",
  language: "en",
  timezone: "UTC",
  country: "",
  website: "",
  description: "",
  offer_type: "services",
  goals: [],
  automation_mode: "human_approved",
  price_disclosure: "quote",
  tools: ["knowledge", "bookings"],
  whatsapp_choice: "existing",
  setup_state: "active",
  onboarding_step: 5,
  completed_steps: [1, 2, 3, 4, 5],
  help_requested_at: null,
  launched_at: null,
  paused_reason: null,
  readiness: [],
  whatsapp: { status: "active" },
  tool_groups: ["knowledge", "bookings"],
  goals_available: ["answer_questions"],
};

const connector = (
  key: "google_calendar" | "shopify",
  state: string,
  extra: Record<string, unknown> = {},
) => ({
  key,
  name: key === "shopify" ? "Shopify" : "Google Calendar",
  description:
    key === "shopify"
      ? "pi can tell customers where their Shopify order is. It cannot change orders."
      : "pi checks your free times and adds confirmed bookings to your calendar.",
  available: true,
  state,
  detail: "",
  health: "unknown",
  last_checked_at: null,
  problem: "",
  ...extra,
});

const MANAGER = [...OWNER, "integrations.read", "integrations.manage"];
const base = {
  "GET /account": account,
  "GET /pi/bookable-services": [],
  "GET /pi/bookings": [],
};

test("an owner connects Google Calendar and returns to a clear result", async ({
  page,
}) => {
  await mockApi(page, MANAGER, {
    ...base,
    "GET /pi/connectors": [
      connector("google_calendar", "not_connected"),
      connector("shopify", "not_connected"),
    ],
    // The real server returns Google's consent URL; the double returns straight here.
    "POST /pi/connectors/google_calendar/start": {
      authorization_url: "/my-pi/tools?google_calendar=connected",
    },
  });
  await page.goto("/my-pi/tools");
  const accounts = page.getByRole("region", { name: "Your accounts" });
  await expect(accounts.getByText("Not connected")).toHaveCount(2);
  const shopify = accounts.getByRole("button", { name: "Connect Shopify" });
  await expect(shopify).toBeDisabled();
  await accounts.getByLabel("Your store address").fill("bright.myshopify.com");
  await expect(shopify).toBeEnabled();
  await accounts
    .getByRole("button", { name: "Connect Google Calendar" })
    .click();
  await expect(
    page.getByText("Google Calendar is connected. pi will use it from now on."),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/my-pi\/tools$/);
  await expect(
    page.getByText("No calendar is connected, so keep these hours up to date."),
  ).toBeVisible();
});

test("connected and broken accounts show honest states and safe actions", async ({
  page,
}) => {
  await mockApi(page, MANAGER, {
    ...base,
    "GET /pi/connectors": [
      connector("google_calendar", "action_required", {
        problem: "The connection expired; reconnect it in Tools",
      }),
      connector("shopify", "connected", {
        detail: "bright.myshopify.com",
        last_checked_at: new Date().toISOString(),
      }),
    ],
    "POST /pi/connectors/shopify/test": {
      ok: true,
      status: "connected",
      message: "Shopify store reachable",
    },
  });
  await page.goto("/my-pi/tools");
  const accounts = page.getByRole("region", { name: "Your accounts" });
  await expect(accounts.getByText("Needs attention")).toBeVisible();
  await expect(
    accounts.getByText("The connection expired; reconnect it in Tools"),
  ).toBeVisible();
  await expect(
    accounts.getByRole("button", { name: "Reconnect" }),
  ).toBeVisible();
  await expect(
    page.getByText("Your Google Calendar needs reconnecting"),
  ).toBeVisible();
  await expect(accounts.getByText("bright.myshopify.com")).toBeVisible();
  await accounts.getByRole("button", { name: "Test connection" }).click();
  await expect(accounts.getByText("Connection works.")).toBeVisible();
  // Disconnecting asks first and explains what happens.
  await accounts.getByRole("button", { name: "Disconnect" }).last().click();
  const confirm = accounts.getByRole("group", { name: "Disconnect Shopify" });
  await expect(
    confirm.getByText(/uninstall the app in your Shopify admin/),
  ).toBeVisible();
  await confirm.getByRole("button", { name: "Keep connected" }).click();
  await expect(confirm).toHaveCount(0);
});

test("unavailable accounts and view-only members get no connect buttons", async ({
  page,
}) => {
  await mockApi(page, [...OWNER, "integrations.read"], {
    ...base,
    "GET /pi/connectors": [
      connector("google_calendar", "not_connected", { available: false }),
      connector("shopify", "connected", { detail: "bright.myshopify.com" }),
    ],
  });
  await page.goto("/my-pi/tools");
  const accounts = page.getByRole("region", { name: "Your accounts" });
  await expect(accounts.getByText("Not available yet")).toBeVisible();
  await expect(
    accounts.getByText(/can't be connected on this Pi server yet/),
  ).toBeVisible();
  await expect(accounts.getByRole("button")).toHaveCount(0);
  await expect(
    accounts.getByText(
      "Ask the business owner or an admin to change this connection.",
    ),
  ).toBeVisible();
});

test("the accounts section fits a 390px screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await mockApi(page, MANAGER, {
    ...base,
    "GET /pi/connectors": [
      connector("google_calendar", "connected"),
      connector("shopify", "not_connected"),
    ],
  });
  await page.goto("/my-pi/tools");
  await expect(
    page.getByRole("region", { name: "Your accounts" }),
  ).toBeVisible();
  expect(await noHorizontalOverflow(page)).toBe(true);
});
