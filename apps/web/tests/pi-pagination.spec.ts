import { test, expect } from "@playwright/test";
import { signIn } from "./helpers";

test("PI inbox loads more conversations and shows an accurate count", async ({
  page,
}) => {
  await signIn(page, "/pi/inbox");
  const list = page.getByRole("list", { name: "Conversations" });
  const rows = list.locator("button[data-conversation]");
  const count = page.getByTestId("conversation-count");
  await expect(rows).toHaveCount(25);
  await expect(count).toHaveText(/^25 of \d+ conversations$/);
  const total = Number((await count.textContent())!.match(/of (\d+)/)![1]);
  expect(total).toBeGreaterThan(25);

  await page
    .getByRole("button", { name: "Load more conversations", exact: true })
    .click();
  await expect(rows).toHaveCount(Math.min(total, 50));
  if (total <= 50) {
    await expect(count).toHaveText(`${total} conversations`);
    await expect(
      page.getByRole("button", { name: "Load more conversations" }),
    ).toHaveCount(0);
  }
  // Rows are unique after merging pages.
  const ids = await rows.evaluateAll((els) =>
    els.map((el) => el.getAttribute("data-conversation")),
  );
  expect(new Set(ids).size).toBe(ids.length);
});

test("PI thread loads older messages without jumping to the bottom", async ({
  page,
}) => {
  await signIn(page, "/pi/inbox");
  // Search also matches message text, including messages not in the preview.
  await page
    .getByPlaceholder("Search customer, phone or message")
    .fill("standing order");
  const rows = page
    .getByRole("list", { name: "Conversations" })
    .locator("button[data-conversation]");
  await expect(rows).toHaveCount(1);
  await rows.first().click();

  const messages = page.getByRole("list", { name: "Messages" });
  await expect(
    messages.getByText("Week 32 draft is ready", { exact: false }),
  ).toBeVisible();
  const oldest = messages.getByText(
    "Starting a weekly standing order: 2 bags of House Espresso, please.",
  );
  await expect(oldest).toHaveCount(0);
  const messageItems = messages.locator(":scope > li:not([role=separator])");
  await expect(messageItems).toHaveCount(50);

  const scroller = page.locator("[aria-live=polite]").filter({ has: messages });
  const loadOlder = page.getByRole("button", {
    name: "Load older messages",
    exact: true,
  });
  await loadOlder.scrollIntoViewIfNeeded();
  await loadOlder.click();
  await expect(oldest).toHaveCount(1);
  await expect(messageItems).toHaveCount(64);
  await expect(loadOlder).toHaveCount(0);
  // The previous first message stays in view instead of jumping to the newest.
  const atBottom = await scroller.evaluate(
    (el) => el.scrollHeight - el.scrollTop - el.clientHeight < 40,
  );
  expect(atBottom).toBe(false);
  await expect(
    messages.getByText("Week 8: same order as last week, please.", {
      exact: true,
    }),
  ).toBeInViewport();
});

test("PI agent publishes a version and tool changes in one step", async ({
  page,
}) => {
  const requests: string[] = [];
  page.on("request", (r) => requests.push(r.url()));
  await signIn(page, "/pi/agents/new");
  await page.getByRole("radio", { name: /^Handoff/ }).click();
  const next = page.getByRole("button", { name: "Continue", exact: true });
  await next.click(); // Instructions
  await next.click(); // Model
  await next.click(); // Tools
  await page.getByRole("checkbox", { name: "Customer memory" }).check();
  await page.getByRole("checkbox", { name: "Create handoff" }).uncheck();
  await next.click(); // Rules & review
  await page
    .getByRole("textbox", { name: /Change note/ })
    .fill("Look up memory before escalating");
  await next.click(); // Publish
  // Reaching the last step must not publish by itself.
  await expect(
    page.getByRole("heading", { name: "Publish", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Publish version", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Publish version", exact: true })
    .click();
  await expect(
    page.getByText(/^Version \d+ published and active$/),
  ).toBeVisible();
  await page.waitForURL(/\/pi\/agents\/agent-[^/]+-handoff$/);
  // Demo data lives in memory, so switch tabs instead of reloading.
  await page.getByRole("tab", { name: "Tools", exact: true }).click();
  await expect(
    page.getByRole("switch", { name: "Customer memory", exact: true }),
  ).toBeChecked();
  await expect(
    page.getByRole("switch", { name: "Create handoff", exact: true }),
  ).not.toBeChecked();
  // Demo mode never calls the API.
  expect(requests.some((u) => u.includes("/api/v1/"))).toBe(false);
});
