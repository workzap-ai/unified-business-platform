import { expect, test } from "@playwright/test";

import { mockApi, noHorizontalOverflow, OWNER } from "./support";

// Business profile page: facts with their source and confirmed state, and confirm, edit and
// delete. API doubles only.

const fact = (id: string, key: string, value: string, over = {}) => ({
  id,
  key,
  value,
  source: "owner",
  confirmed: true,
  confirmed_at: new Date().toISOString(),
  evidence: "",
  url: "",
  fetched_at: null,
  ...over,
});

const profiles = {
  items: [
    {
      id: "p1",
      customer_id: "c1",
      customer_name: "Ata",
      display_name: "Ata Clothing",
      what_they_do: "Baby clothes",
      updated_at: new Date().toISOString(),
      facts: [
        fact("f1", "what_they_do", "Baby clothes"),
        fact("f2", "business_name", "Ata Clothing", {
          source: "page",
          confirmed: false,
          confirmed_at: null,
        }),
        fact("f3", "website", "none"),
      ],
      snapshots: [],
    },
  ],
};

test("facts show their source and state, and a page fact offers Confirm", async ({
  page,
}) => {
  await mockApi(page, OWNER, { "GET /pi/business-profiles": profiles });
  await page.goto("/brain/profile");
  await expect(page.getByTestId("business-profile")).toContainText(
    "Ata Clothing",
  );
  const name = page.getByTestId("fact-business_name");
  await expect(name).toContainText("From their page");
  await expect(name).toContainText("Not confirmed yet");
  await expect(page.getByTestId("fact-what_they_do")).toContainText(
    "Told by the owner",
  );
  await expect(page.getByTestId("fact-website")).toContainText("No website");
  await expect(name.getByRole("button", { name: "Confirm" })).toBeVisible();
  await expect(
    page
      .getByTestId("fact-what_they_do")
      .getByRole("button", { name: "Confirm" }),
  ).toHaveCount(0);
  await noHorizontalOverflow(page);
});

test("a viewer without access sees no profiles", async ({ page }) => {
  await mockApi(page, ["pi.read"], { "GET /pi/business-profiles": profiles });
  await page.goto("/brain/profile");
  await expect(page.getByText("You can't see business profiles")).toBeVisible();
});
