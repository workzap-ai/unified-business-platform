import { expect, test } from "@playwright/test";

import { mockApi, OWNER } from "./support";

const ACCOUNT = {
  name: "Zara Boutique",
  business_category: "Clothing",
  language: "en",
  timezone: "Asia/Karachi",
  country: "PK",
  currency: "PKR",
  website: "",
  description: "",
  offer_type: "services",
  goals: [],
  automation_mode: "human_approved",
  price_disclosure: "quote",
  tools: ["knowledge"],
  whatsapp_choice: null,
  setup_state: "draft",
  onboarding_step: 3,
  completed_steps: [1, 2],
  help_requested_at: null,
  launched_at: null,
  paused_reason: null,
  readiness: [],
  whatsapp: { status: "draft" },
  tool_groups: ["knowledge"],
  goals_available: ["answer_questions"],
};

test("a business picks a ready number from the pool", async ({ page }) => {
  await mockApi(page, [...OWNER, "pi.whatsapp.manage"], {
    "GET /account": ACCOUNT,
    "GET /whatsapp": {
      production: { status: "draft" },
      test: { status: "draft" },
      provider_available: true,
      new_number_countries: [],
    },
    "GET /whatsapp/numbers": [
      {
        id: "n1",
        display_phone_number: "+1 415 555 0101",
        country: "US",
        price_label: "Included in Growth",
        coexistence: false,
        display_name_status: "APPROVED",
        offered_to_you: false,
      },
      {
        id: "n2",
        display_phone_number: "+1 415 555 0102",
        country: "US",
        price_label: "",
        coexistence: false,
        display_name_status: "APPROVED",
        offered_to_you: true,
      },
    ],
  });
  await page.goto("/setup?step=3");
  await expect(page.getByText("Choose a number from us")).toBeVisible();
  await expect(page.getByText("+1 415 555 0101")).toBeVisible();
  await expect(page.getByText("Offered to you")).toBeVisible();
  // The advanced option is still there for businesses keeping their own number.
  await page.getByText("Use my own number (advanced)").click();
  await expect(
    page.getByRole("button", { name: "Connect WhatsApp" }).last(),
  ).toBeVisible();
  await page.getByText("Choose a number from us").click();
  const chosen = page.waitForRequest(
    (r) => r.url().includes("/whatsapp/numbers/") && r.method() === "POST",
  );
  await page.getByText("+1 415 555 0101").click();
  await page.getByRole("button", { name: "Use this number" }).click();
  expect((await chosen).url()).toContain("/whatsapp/numbers/n1/choose");
});
