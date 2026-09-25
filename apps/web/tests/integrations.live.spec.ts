import { test, expect, type APIRequestContext } from "@playwright/test";
import { z } from "zod";
import { pageSchema } from "../src/services/api-client";
import {
  apiKeyCreatedSchema,
  apiKeySchema,
  connectionDetailSchema,
  connectionSchema,
  definitionSchema,
  deliverySchema,
  eventTypeSchema,
  failureSchema,
  healthSchema,
  inboundEventSchema,
  syncJobSchema,
  testResultSchema,
  webhookSubscriptionCreatedSchema,
  webhookSubscriptionSchema,
} from "../src/features/integrations/types";

/**
 * Contract check: every integrations endpoint the web app calls must parse with the
 * web app's own Zod schema. Runs against a live API. By default it registers a
 * throwaway workspace; set LIVE_EMAIL/LIVE_PASSWORD/LIVE_TENANT/LIVE_ENVIRONMENT_KEY to
 * use an existing (non-production) environment instead.
 */
test("integrations API responses match the web contract", async ({
  page,
  baseURL,
}) => {
  const origin = new URL(baseURL!).origin;
  const api = page.request;
  if (process.env.LIVE_EMAIL) {
    const login = await api.post("/api/v1/auth/login", {
      data: {
        email: process.env.LIVE_EMAIL,
        password: process.env.LIVE_PASSWORD,
      },
      headers: { origin },
    });
    expect(login.ok()).toBeTruthy();
  } else {
    const register = await api.post("/api/v1/auth/register", {
      data: {
        email: `contract-${Date.now()}@example.com`,
        password: "Contract-Check-Password-2026!",
        display_name: "Contract Check",
        organization_name: `Contract ${Date.now()}`,
      },
      headers: { origin },
    });
    expect(register.ok()).toBeTruthy();
  }
  const csrf = async () =>
    (await page.context().cookies()).find((c) => c.name === "platform_csrf")!
      .value;
  const headers = async () => ({ origin, "x-csrf-token": await csrf() });

  if (process.env.LIVE_TENANT) {
    const tenants = await (
      await api.get("/api/v1/tenants?page_size=100")
    ).json();
    const tenant = tenants.items.find(
      (t: { name: string }) => t.name === process.env.LIVE_TENANT,
    );
    await api.put("/api/v1/auth/session/workspace", {
      data: { tenant_id: tenant.id, environment_id: null },
      headers: await headers(),
    });
    const envs = await (await api.get("/api/v1/environments")).json();
    const list = Array.isArray(envs) ? envs : envs.items;
    const env = list.find(
      (e: { key: string; kind: string }) =>
        e.key === process.env.LIVE_ENVIRONMENT_KEY,
    );
    expect(env.kind).not.toBe("production");
    const switched = await api.put("/api/v1/auth/session/workspace", {
      data: { tenant_id: tenant.id, environment_id: env.id },
      headers: await headers(),
    });
    expect(switched.ok()).toBeTruthy();
  }

  const problems: string[] = [];
  async function check<T>(
    label: string,
    schema: z.ZodType<T>,
    call: (
      r: APIRequestContext,
    ) => Promise<import("@playwright/test").APIResponse>,
  ): Promise<T | undefined> {
    const response = await call(api);
    if (!response.ok()) {
      problems.push(
        `${label}: HTTP ${response.status()} ${await response.text()}`,
      );
      return undefined;
    }
    const parsed = schema.safeParse(await response.json());
    if (!parsed.success) {
      problems.push(
        `${label}: ${parsed.error.issues
          .slice(0, 5)
          .map((i) => `${i.path.join(".")} ${i.message}`)
          .join("; ")}`,
      );
      return undefined;
    }
    return parsed.data;
  }
  const P = "/api/v1/integrations";

  await check("definitions", z.array(definitionSchema), (r) =>
    r.get(`${P}/definitions`),
  );
  await check("event-types", z.array(eventTypeSchema), (r) =>
    r.get(`${P}/event-types`),
  );
  const created = await check(
    "create connection",
    connectionSchema,
    async (r) =>
      r.post(`${P}/connections`, {
        headers: await headers(),
        data: {
          integration_key: "generic_webhook",
          display_name: `Contract hook ${Date.now()}`,
          mode: "production",
          config: { url: "https://example.com/contract-check" },
          credentials: { signing_secret: "contract-check-signing-secret" },
        },
      }),
  );
  await check("connections", pageSchema(connectionSchema), (r) =>
    r.get(`${P}/connections?page_size=25`),
  );
  if (created) {
    await check("connection detail", connectionDetailSchema, (r) =>
      r.get(`${P}/connections/${created.id}`),
    );
    await check("test connection", testResultSchema, async (r) =>
      r.post(`${P}/connections/${created.id}/test`, {
        headers: await headers(),
      }),
    );
    await check("disable", connectionDetailSchema, async (r) =>
      r.post(`${P}/connections/${created.id}/disable`, {
        headers: await headers(),
      }),
    );
    const removed = await api.delete(`${P}/connections/${created.id}`, {
      headers: await headers(),
    });
    if (removed.status() !== 204)
      problems.push(`disconnect: HTTP ${removed.status()}`);
  }
  const hook = await check(
    "create webhook",
    webhookSubscriptionCreatedSchema,
    async (r) =>
      r.post(`${P}/webhooks`, {
        headers: await headers(),
        data: {
          name: "Contract check",
          url: "https://example.com/contract-webhook",
          event_types: ["order.confirmed"],
          enabled: false,
        },
      }),
  );
  await check("webhooks", pageSchema(webhookSubscriptionSchema), (r) =>
    r.get(`${P}/webhooks`),
  );
  if (hook) {
    await check("deliveries", pageSchema(deliverySchema), (r) =>
      r.get(`${P}/webhooks/${hook.id}/deliveries`),
    );
    await api.delete(`${P}/webhooks/${hook.id}`, { headers: await headers() });
  }
  await check("events", pageSchema(inboundEventSchema), (r) =>
    r.get(`${P}/events`),
  );
  await check("jobs", pageSchema(syncJobSchema), (r) => r.get(`${P}/jobs`));
  await check("failures", pageSchema(failureSchema), (r) =>
    r.get(`${P}/failures`),
  );
  await check("health", healthSchema, (r) => r.get(`${P}/health`));
  const key = await check("create api key", apiKeyCreatedSchema, async (r) =>
    r.post(`${P}/api-keys`, {
      headers: await headers(),
      data: {
        name: "Contract check",
        scopes: ["customers.read"],
        expires_in_days: 1,
      },
    }),
  );
  await check("api keys", z.array(apiKeySchema), (r) => r.get(`${P}/api-keys`));
  if (key)
    await api.delete(`${P}/api-keys/${key.id}`, { headers: await headers() });

  expect(problems).toEqual([]);
});
