import { test, expect, type Page } from "@playwright/test";
import registry from "../src/features/navigation/registry.generated.json";
import access from "../src/features/auth/access.generated.json";
import { resolveNavigation } from "../src/features/navigation/resolve";
import type { NavDefinition } from "../src/features/navigation/types";

// Contract-backed UI flows for the Solutions tab (live HTTP adapter, deterministic responses).
// Needs a live-mode build (see playwright.live.config.ts). Server rules live in API tests.
const version = (v: string, status: string) => ({
  version: v,
  status,
  changes: v === "1.0" ? [] : ["sample_reply"],
  evidence: { candidates: 3 },
  created_at: "2026-10-20T10:00:00Z",
  rolled_back_at: null,
});

async function open(page: Page, opts: { rollbackError?: boolean } = {}) {
  const permissions = access.roles.find((r) => r.key === "owner")!.permissions;
  const posts: { path: string; body: unknown }[] = [];
  await page
    .context()
    .addCookies([
      { name: "platform_csrf", value: "t", url: "http://127.0.0.1:3100" },
    ]);
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    const method = route.request().method();
    let status = 200;
    let body: unknown = {};
    if (path === "/auth/session")
      body = {
        user: {
          id: "u1",
          display_name: "Owner",
          email: "o@example.com",
          email_verified: true,
        },
        tenant: { id: "t1", name: "Test" },
        environment: { id: "e1", name: "Production", kind: "production" },
        branch: null,
        roles: ["owner"],
        permissions,
      };
    else if (path === "/navigation")
      body = resolveNavigation(registry as NavDefinition[], {
        permissions: new Set(permissions),
        roles: new Set(["owner"]),
        products: { pi: [] },
        environmentKind: "production",
      });
    else if (path === "/tenants" || path === "/environments") body = [];
    else if (method === "POST" && path.startsWith("/pi/solutions")) {
      posts.push({ path, body: route.request().postDataJSON() });
      if (path.endsWith("/rollback") && opts.rollbackError) {
        status = 409;
        body = {
          error: {
            code: "NOTHING_TO_ROLL_BACK",
            message: "This industry is already on its starting version",
            request_id: "r1",
          },
        };
      } else
        body = { industry: "dairy", rolled_back: "1.2", id: "x", status: "ok" };
    } else if (path === "/pi/solutions")
      body = {
        industries: [
          {
            industry: "dairy",
            seeded: true,
            latest: version("1.2", "live"),
            versions: 2,
          },
        ],
      };
    else if (path === "/pi/solutions/review")
      body = {
        ideas: [
          {
            id: "a1",
            industry: "dairy",
            problem: "late_delivery",
            language: "en",
            text: "Offer a cold-chain check",
            kind: "process",
            status: "review",
            uses: 0,
            source: "learned",
            traffic_cap: 0.1,
            feedback: 0,
            retired_reason: "",
          },
        ],
        proposals: [],
      };
    else if (path === "/pi/solutions/dairy")
      body = {
        industry: "dairy",
        sample_reply: { person: "Milk is late", pi: "Which route?" },
        versions: [version("1.2", "live"), version("1.0", "live")],
        ideas: 0,
      };
    else if (path === "/pi/solutions/arms") body = { items: [] };
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  await page.goto("/pi/brain?tab=solutions");
  await expect(page.getByText("Industries that have learned")).toBeVisible();
  return posts;
}

test("rollback asks first, names the scope, and rolls back only that industry", async ({
  page,
}) => {
  const posts = await open(page);
  await page.getByRole("button", { name: /dairy/ }).click();
  await page
    .getByRole("button", { name: "Roll back latest learned version" })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Only this industry is affected");
  await expect(dialog).toContainText("@1.0 never rolls back");
  expect(posts).toEqual([]);
  await dialog.getByRole("button", { name: "Roll back" }).click();
  await expect
    .poll(() => posts.map((p) => p.path))
    .toEqual(["/pi/solutions/dairy/rollback"]);
});

test("a refused rollback shows the API message in the dialog", async ({
  page,
}) => {
  await open(page, { rollbackError: true });
  await page.getByRole("button", { name: /dairy/ }).click();
  await page
    .getByRole("button", { name: "Roll back latest learned version" })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Roll back" })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "This industry is already on its starting version",
  );
});

test("rejecting an idea needs a reason before anything is sent", async ({
  page,
}) => {
  const posts = await open(page);
  await page.getByRole("button", { name: "Reject this idea" }).click();
  const confirm = page.getByRole("button", { name: "Confirm reject" });
  await expect(confirm).toBeDisabled();
  await page
    .getByRole("textbox", { name: "Reason for rejecting this idea" })
    .fill("touches pricing");
  expect(posts).toEqual([]);
  await confirm.click();
  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0]).toEqual({
    path: "/pi/solutions/ideas/a1/decide",
    body: { approve: false, reason: "touches pricing" },
  });
});
