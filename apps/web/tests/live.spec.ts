import { test, expect } from "@playwright/test";
import * as schema from "../src/features/pi/contracts.generated";
import { z } from "zod";

test("live registration, service offering, PI contracts and workspace pages", async ({
  page,
  baseURL,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/register");
  await page.getByLabel("Your name").fill("Live Verification");
  await page
    .getByLabel("Business name")
    .fill(`Service Verification ${Date.now()}`);
  await page.getByLabel("Work email").fill(`verify-${Date.now()}@example.com`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("Verified-Service-Test-2026!");
  await page
    .getByRole("button", { name: "Create workspace", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ }),
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
  await expect(
    page
      .getByRole("navigation", { name: "Primary" })
      .getByText("Inventory", { exact: true }),
  ).toHaveCount(0);
  await page.goto("/catalog/products/new");
  await page.getByLabel("Offering name").fill("Live website implementation");
  await page.locator("#variant-0-sku").fill(`LIVE-${Date.now()}`);
  await page.locator("#variant-0-name").fill("Implementation");
  await page.locator("#variant-0-price").fill("1500.00");
  await page.getByRole("button", { name: "Create offering" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Live website implementation",
      exact: true,
    }),
  ).toBeVisible();
  const csrf = (await page.context().cookies()).find(
    (x) => x.name === "platform_csrf",
  )!.value;
  const headers = { "x-csrf-token": csrf, origin: new URL(baseURL!).origin };
  expect(
    (
      await page.request.post("/api/v1/products/pi/install", {
        data: {},
        headers,
      })
    ).ok(),
  ).toBeTruthy();
  expect(
    (
      await page.request.put("/api/v1/products/pi/environment", {
        data: { enabled: true },
        headers,
      })
    ).ok(),
  ).toBeTruthy();
  const contracts: [string, z.ZodType][] = [
    ["/pi/overview", schema.PiOverviewSchema],
    ["/pi/settings", schema.PiSettingsSchema],
    ["/pi/agents", z.array(schema.AgentSchema)],
    ["/pi/tools", z.array(schema.ToolDefinitionSchema)],
    ["/pi/analytics?range=30", schema.PiAnalyticsSchema],
    ["/pi/whatsapp", schema.WhatsAppConnectionSchema.nullable()],
    ["/pi/knowledge/sources", z.array(schema.KnowledgeSourceSchema)],
    ["/pi/knowledge/documents", z.array(schema.KnowledgeDocumentSchema)],
  ];
  for (const [path, validator] of contracts) {
    const response = await page.request.get(`/api/v1${path}`);
    expect(response.status(), path).toBe(200);
    const parsed = validator.safeParse(await response.json());
    expect(
      parsed.success,
      `${path}: ${parsed.success ? "" : parsed.error.message}`,
    ).toBeTruthy();
  }
  const failures: string[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/api/v1/") && response.status() >= 400)
      failures.push(`${response.status()} ${new URL(response.url()).pathname}`);
  });
  for (const path of [
    "/customers",
    "/catalog",
    "/sales",
    "/quotes",
    "/orders",
    "/billing",
    "/finance",
    "/hr",
    "/reports",
    "/workflows",
    "/pi",
    "/pi/inbox",
    "/pi/agents",
    "/pi/knowledge",
    "/pi/analytics",
    "/pi/settings",
  ]) {
    await page.goto(path);
    await expect(page.locator("main h1").first(), path).toBeVisible();
    await expect(
      page.getByText("Something went wrong", { exact: true }),
    ).toHaveCount(0);
  }
  await page.goto("/workflows");
  await page.getByRole("button", { name: "Run review" }).first().click();
  await expect(page.getByRole("heading", { name: /completed/i })).toBeVisible();
  // Exercise the saved approval UI through the entire quote/order lifecycle.
  const create = async (path: string, data: unknown) => {
    const response = await page.request.post(`/api/v1/${path}`, { data, headers });
    expect(response.ok(), `${path}: ${response.status()}`).toBeTruthy();
    return response.json();
  };
  const customer = await create("customers", { name: "Workflow browser client", tags: [] });
  const offerings = await (await page.request.get("/api/v1/catalog/products")).json();
  const offering = await (await page.request.get(`/api/v1/catalog/products/${offerings.items[0].id}`)).json();
  const quote = await create("quotes", { customer_id: customer.id, lines: [{ variant_id: offering.variants[0].id, quantity: 1 }] });
  await page.goto("/workflows");
  const approveAction = async (kind: string, id: string, action: string) => {
    await page.getByLabel("Record type", { exact: true }).selectOption(kind);
    await page.getByLabel("Business record", { exact: true }).selectOption(id);
    await page.getByLabel("Action", { exact: true }).selectOption(`${kind}.${action}`);
    await page.getByRole("button", { name: "Prepare review", exact: true }).click();
    await expect(page.getByRole("button", { name: "Approve and run", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Approve and run", exact: true }).click();
    await expect(page.getByRole("heading", { name: new RegExp(`${kind} ${action.replaceAll("_", " ")}.*completed`, "i") })).toBeVisible();
  };
  for (const action of ["submit", "send", "accept", "convert"]) {
    await approveAction("quotes", quote.id, action);
  }
  const accepted = await (await page.request.get(`/api/v1/quotes/${quote.id}`)).json();
  for (const action of ["confirm", "start_processing", "complete"]) {
    await approveAction("orders", accepted.order_id, action);
  }
  const delivered = await (await page.request.get(`/api/v1/orders/${accepted.order_id}`)).json();
  expect(delivered.status).toBe("delivered");
  await page.goto(`/billing/invoices/${delivered.invoice_id}`);
  await page.getByRole("button", { name: "Record payment", exact: true }).click();
  const payment = page.getByRole("dialog", { name: "Record payment" });
  await payment.getByLabel("Reference", { exact: true }).fill("BROWSER-VERIFIED");
  await payment.getByRole("button", { name: "Record payment", exact: true }).click();
  await expect(payment).not.toBeVisible();
  const paid = await (await page.request.get(`/api/v1/billing/invoices/${delivered.invoice_id}`)).json();
  expect(paid.status).toBe("paid");
  expect(paid.balance_due).toBe("0.00");
  const original = await (
    await page.request.get("/api/v1/auth/session")
  ).json();
  await page.goto("/workspaces/new");
  await page.getByLabel("Workspace name").fill("Second live workspace");
  await page
    .getByRole("button", { name: "Create workspace", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: /Workspace: Second live workspace/ }),
  ).toBeVisible();
  const second = await (await page.request.get("/api/v1/auth/session")).json();
  expect(second.user.id).toBe(original.user.id);
  expect(
    (await (await page.request.get("/api/v1/catalog/products")).json()).total,
  ).toBe(0);
  const environmentResponse = await page.request.post("/api/v1/environments", {
    data: { key: "staging", name: "Staging", kind: "staging" },
    headers,
  });
  expect(environmentResponse.ok()).toBeTruthy();
  await page.reload();
  await page.getByRole("button", { name: /Environment: Production/ }).click();
  await page.getByRole("button", { name: /Staging staging/ }).click();
  await expect(
    page.getByRole("button", { name: /Environment: Staging/ }),
  ).toBeVisible();
  expect(
    (await (await page.request.get("/api/v1/customers")).json()).total,
  ).toBe(0);
  await page
    .getByRole("button", { name: /Workspace: Second live workspace/ })
    .click();
  await page
    .getByRole("button")
    .filter({ has: page.getByText(original.tenant.name, { exact: true }) })
    .click();
  await expect(
    page.getByRole("button", {
      name: new RegExp(`Workspace: ${original.tenant.name}`),
    }),
  ).toBeVisible();
  expect(
    (await (await page.request.get("/api/v1/catalog/products")).json()).total,
  ).toBe(1);
  await page.goto("/workflows");
  for (const width of [390, 430, 768, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBeTruthy();
  }
  expect(errors).toEqual([]);
  expect(failures).toEqual([]);
});
