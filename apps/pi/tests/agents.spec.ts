import { expect, test } from "@playwright/test";

import { mockApi, OWNER } from "./support";

const agent = (key: string, name: string) => ({
  id: `a-${key}`,
  key,
  name,
  role: "",
  description: "",
  enabled: true,
  current_version: 1,
  model_alias: "fast",
  temperature: "0.2",
  tools: [],
  runs_7d: 0,
  success_rate: 0,
  avg_latency_ms: 0,
  last_run_at: null,
});

const AGENTS = [
  agent("router", "Router"),
  agent("requirement", "Requirement"),
  agent("support", "Support"),
];

test("in brain mode the Enquiries agent is the brain card and the rest are collapsed", async ({
  page,
}) => {
  await mockApi(page, [...OWNER, "pi.agents.manage"], {
    "GET /pi/agents": AGENTS,
    "GET /pi/settings": { response_rules: { pi_mode: "brain" } },
  });
  await page.goto("/my-pi/agents");
  const card = page.getByTestId("brain-agent-card");
  await expect(card).toContainText("Brain agent");
  await expect(card).toContainText("Enquiries");
  await expect(card).toContainText(
    "Guidance cannot override pi's safety rules",
  );
  const summary = page.getByText(/Not used in brain mode \(2 helpers\)/);
  await expect(summary).toBeVisible();
  await expect(page.getByRole("heading", { name: "Front desk" })).toBeHidden();
  await summary.click();
  await expect(page.getByRole("heading", { name: "Front desk" })).toBeVisible();
});

test("the routing test box says it is a preview only", async ({ page }) => {
  await mockApi(page, [...OWNER, "pi.agents.manage"], {
    "GET /pi/agents/a-requirement": AGENTS[1],
    "GET /pi/settings": { response_rules: { pi_mode: "brain" } },
  });
  await page.goto("/my-pi/agents/a-requirement");
  await expect(page.getByText("Brain agent").first()).toBeVisible();
  await page.getByRole("tab", { name: "Test" }).click();
  await expect(page.getByText(/Routing preview only/).first()).toBeVisible();
});
