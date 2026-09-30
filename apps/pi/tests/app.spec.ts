import { expect, test } from "@playwright/test";

import { OWNER, VIEWER, mockApi, noHorizontalOverflow } from "./support";

test("signed-out visitors are sent to sign in", async ({ page }) => {
  await page.route("**/api/v1/pi-app/auth/session", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({
        error: { code: "UNAUTHENTICATED", message: "x" },
      }),
    }),
  );
  await page.goto("/home");
  await expect(page).toHaveURL(/\/sign-in\?next=%2Fhome/);
  await expect(
    page.getByRole("heading", { name: "Welcome back" }),
  ).toBeVisible();
});

test("home shows honest status and next actions", async ({ page }) => {
  await mockApi(page, OWNER);
  await page.goto("/home");
  await expect(
    page.getByRole("heading", { name: "Pi is answering your customers" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: /1 replies to approve/ }),
  ).toBeVisible();
});

test("an AI outage is shown instead of 'active'", async ({ page }) => {
  await mockApi(page, OWNER, {
    "GET /home": {
      name: "Brightline Studio",
      setup_state: "active",
      active: true,
      plan_reason: null,
      metrics: {
        conversations_7d: 2,
        pi_replies_7d: 0,
        enquiries_7d: 0,
        waiting_for_team: 2,
        awaiting_approval: 0,
        open_questions: 0,
        unread: 0,
        ai_unavailable_24h: 2,
      },
      next_actions: [],
    },
  });
  await page.goto("/home");
  await expect(
    page.getByRole("heading", {
      name: "Pi is on, but couldn't reply recently",
    }),
  ).toBeVisible();
});

test("inbox pages conversations, loads older history and lets an owner approve", async ({
  page,
}) => {
  await mockApi(page, OWNER);
  await page.goto("/inbox?conversation=1");
  await expect(page.getByText("30 conversations")).toBeVisible();
  await expect(page.getByRole("button", { name: "Load more" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Load older messages" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve and send" }),
  ).toBeVisible();
  await expect(page.getByText("Waiting for approval")).toBeVisible();
});

test("view-only members cannot reply, take over or approve", async ({
  page,
}) => {
  await mockApi(page, VIEWER);
  await page.goto("/inbox?conversation=1");
  await expect(
    page.getByText("You can view this conversation but not reply."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Take over" })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Approve and send" }),
  ).toHaveCount(0);
});

test("unavailable tools are clearly marked and cannot be switched on", async ({
  page,
}) => {
  await mockApi(page, OWNER, {
    "GET /account": {
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
      tools: ["knowledge"],
      whatsapp_choice: "existing",
      setup_state: "draft",
      onboarding_step: 4,
      completed_steps: [1, 2],
      help_requested_at: null,
      launched_at: null,
      paused_reason: null,
      readiness: [],
      whatsapp: { status: "draft" },
      // "campaigns" stands in for a group the server lists before this release supports it.
      tool_groups: ["knowledge", "bookings", "payments", "campaigns"],
      goals_available: ["answer_questions"],
    },
  });
  await page.goto("/setup?step=4");
  const future = page.getByRole("checkbox", { name: /campaigns/ });
  await expect(future).toBeDisabled();
  await expect(page.getByText("Not available yet")).toHaveCount(1);
  await expect(page.getByRole("checkbox", { name: /Bookings/ })).toBeEnabled();
  await expect(page.getByRole("checkbox", { name: /Payments/ })).toBeEnabled();
});

for (const width of [390, 1440]) {
  test(`key screens fit a ${width}px screen`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockApi(page, OWNER);
    for (const path of [
      "/home",
      "/inbox",
      "/inbox?conversation=1",
      "/sign-in",
      "/sign-up",
    ]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      expect(await noHorizontalOverflow(page), path).toBe(true);
    }
  });
}
