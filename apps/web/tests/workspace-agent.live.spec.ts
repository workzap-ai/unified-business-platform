import { test, expect, type Page } from "@playwright/test";
import registry from "../src/features/navigation/registry.generated.json";
import access from "../src/features/auth/access.generated.json";
import { resolveNavigation } from "../src/features/navigation/resolve";
import type { NavDefinition } from "../src/features/navigation/types";

// Contract-backed UI tests; real permission/transaction checks live in API integration tests.
async function workspace(page: Page, role = "owner") {
  const permissions = access.roles.find((r) => r.key === role)!.permissions;
  const session = {
    user: {
      id: "user-1",
      display_name: "Test Owner",
      email: "owner@example.com",
    },
    tenant: { id: "tenant-1", name: "Agent Test Workspace" },
    environment: { id: "env-1", name: "Production", kind: "production" },
    branch: null,
    roles: [role],
    permissions,
  };
  const allowed =
    role === "owner"
      ? [
          "employees.create",
          "employees.update",
          "tasks.create",
          "tasks.update",
          "customers.create",
        ]
      : [];
  const drafts: Record<string, unknown>[] = [];
  const decisions: string[] = [];
  await page
    .context()
    .addCookies([
      {
        name: "platform_csrf",
        value: "test-csrf",
        url: "http://127.0.0.1:3337",
      },
    ]);
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    const method = route.request().method();
    let body: unknown = {};
    if (path === "/auth/session") body = session;
    else if (path === "/navigation")
      body = resolveNavigation(registry as NavDefinition[], {
        permissions: new Set(permissions),
        roles: new Set([role]),
        products: {},
        environmentKind: "production",
      });
    else if (path === "/tenants")
      body = {
        items: [
          { id: "tenant-1", name: "Agent Test Workspace", slug: "agent" },
        ],
        page: 1,
        page_size: 25,
        total: 1,
      };
    else if (path === "/environments")
      body = [
        {
          id: "env-1",
          key: "production",
          name: "Production",
          kind: "production",
          status: "active",
          is_default: true,
        },
      ];
    else if (path === "/workspace-agent/context")
      body = {
        name: "Test Owner",
        user_id: "user-1",
        membership_id: "member-1",
        tenant_id: "tenant-1",
        environment_id: "env-1",
        roles: [role],
        permissions,
        read_areas:
          role === "owner"
            ? ["employees", "tasks", "customers", "members"]
            : ["customers", "tasks"],
        actions: allowed,
        specialists: ["hr", "finance", "crm", "operations"],
        ai_enabled: false,
      };
    else if (path === "/workspace-agent/proposals" && method === "GET")
      body = drafts.filter((d) => d.status === "pending");
    else if (path === "/workspace-agent/proposals" && method === "POST") {
      const input = route.request().postDataJSON();
      const draft = {
        id: `draft-${drafts.length + 1}`,
        operation: input.operation,
        preview: input.arguments,
        status: "pending",
        expires_at: new Date(Date.now() + 1800000).toISOString(),
        result: null,
      };
      drafts.push(draft);
      body = draft;
    } else if (path.includes("/decision")) {
      const input = route.request().postDataJSON();
      decisions.push(input.decision);
      const draft = drafts.find((d) => path.includes(String(d.id)))!;
      draft.status = input.decision === "confirm" ? "applied" : "cancelled";
      draft.result =
        input.decision === "confirm" ? { count: 1, ids: ["record-1"] } : null;
      body = draft;
      expect(route.request().headers()["x-workspace-tenant"]).toBe("tenant-1");
      expect(route.request().headers()["x-csrf-token"]).toBe("test-csrf");
    } else if (path === "/workspace-agent/chat")
      body = {
        message: "Workspace checked. Your authorized records are available.",
        results: [],
        proposals: [],
        mode: "tools",
        navigate: null,
      };
    else if (path === "/workspace-agent/read") {
      const area = route.request().postDataJSON().area;
      body = {
        area,
        specialist: "operations",
        route: "/workspace-agent",
        items: [],
        total: 0,
        page: 1,
        page_size: 25,
      };
    } else if (path === "/workspace-agent/documents") {
      expect(route.request().postData()).toContain("employees");
      const draft = {
        id: "import-1",
        operation: "employees.create",
        preview: {
          rows: [
            {
              full_name: "CSV Employee",
              job_title: "Engineer",
              employment_type: "full_time",
              hire_date: "2026-10-01",
            },
          ],
        },
        status: "pending",
        expires_at: new Date(Date.now() + 1800000).toISOString(),
        result: null,
      };
      drafts.push(draft);
      body = {
        message: "Employee import preview ready.",
        results: [],
        proposals: [draft],
        mode: "tools",
      };
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  await page.goto("/workspace-agent");
  await expect(
    page.getByRole("heading", { name: "Pi Agent Beta" }),
  ).toBeVisible();
  return { drafts, decisions };
}

test("chat and explicit employee approval work without exposing account credentials", async ({
  page,
}) => {
  const state = await workspace(page);
  await page.getByText("Prepare a change", { exact: true }).click();
  await page
    .getByRole("combobox", { name: "Action", exact: true })
    .selectOption("employees.create");
  await page.getByLabel("Full name").fill("Ayesha Khan");
  await page.getByLabel("Job title").fill("Engineer");
  await page.getByLabel("Hire date").fill("2026-10-01");
  await page.getByRole("button", { name: "Preview change" }).click();
  await expect(
    page.getByRole("article", { name: "Action preview" }),
  ).toContainText("Ayesha Khan");
  expect(state.decisions).toEqual([]);
  await page.getByRole("button", { name: "Confirm changes" }).click();
  await expect(page.getByText("1 record(s) saved.")).toBeVisible();
  expect(state.decisions).toEqual(["confirm"]);
  await page.getByLabel("Message Pi Agent").fill("Meri permissions kya hain?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(
    page.getByText("Workspace checked. Your authorized records are available."),
  ).toBeVisible();
});

test("CSV upload creates a reviewable draft and cancellation does not confirm", async ({
  page,
}) => {
  const state = await workspace(page);
  await page.getByLabel("Upload purpose").selectOption("employees");
  await page
    .getByLabel("Upload document", { exact: true })
    .setInputFiles({
      name: "staff.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(
        "full_name,job_title,employment_type,hire_date\nCSV Employee,Engineer,full_time,2026-10-01",
      ),
    });
  await expect(page.getByText("Employee import preview ready.")).toBeVisible();
  await page.getByRole("button", { name: "Cancel draft" }).click();
  await expect(page.getByText("Draft cancelled.")).toBeVisible();
  expect(state.decisions).toEqual(["cancel"]);
});

test("viewer sees the assistant but no employee creation or import", async ({
  page,
}) => {
  await workspace(page, "viewer");
  await expect(page.getByText("Prepare a change", { exact: true })).toHaveCount(
    0,
  );
  await expect(
    page.getByLabel("Upload purpose").locator('option[value="employees"]'),
  ).toHaveCount(0);
  await page.getByRole("tab", { name: "tasks", exact: true }).click();
  await expect(page.getByText("No tasks yet.", { exact: false })).toBeVisible();
});

test("mobile launcher opens an accessible assistant drawer on another page", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await workspace(page);
  await page.goto("/customers");
  await page.getByRole("button", { name: "Open Pi Agent Beta" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByLabel("Message Pi Agent")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
});
