import { expect, test } from "@playwright/test";

import { mockApi, OWNER } from "./support";

const ACCOUNT = {
  name: "Noor Tailors",
  business_category: "Tailoring",
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
  whatsapp_choice: "existing",
  setup_state: "active",
  onboarding_step: 5,
  completed_steps: [1, 2, 3, 4, 5],
  help_requested_at: null,
  launched_at: null,
  paused_reason: null,
  readiness: [],
  whatsapp: { status: "connected" },
  tool_groups: ["knowledge"],
  goals_available: ["answer_questions"],
};

test("a file upload is sent as multipart and becomes a draft to review", async ({
  page,
}) => {
  await mockApi(page, OWNER, {
    "GET /account": ACCOUNT,
    "GET /knowledge/drafts": [],
    "GET /pi/knowledge/documents": [],
  });
  await page.goto("/my-pi/knowledge");
  await expect(
    page.getByRole("heading", { name: /Teach from a file or voice note/ }),
  ).toBeVisible();
  const request = page.waitForRequest(
    (r) => r.url().endsWith("/knowledge/upload") && r.method() === "POST",
  );
  await page.locator("#teach-file").setInputFiles({
    name: "price-list.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n% test file"),
  });
  const sent = await request;
  expect(sent.headers()["content-type"]).toContain("multipart/form-data");
  expect(sent.headers()["x-csrf-token"]).toBeDefined();
  await expect(
    page.getByText(/Pi read it\. Review the draft below/),
  ).toBeVisible();
});
