import type { Page, Route } from "@playwright/test";

// Network-level API doubles for layout/state tests. These are clearly test fixtures,
// never shown in the product; live journeys run against the real API (see README).

export const session = (permissions: string[], setup_state = "active") => ({
  user: { id: "u1", email: "owner@example.com", display_name: "Amina" },
  business: {
    id: "b1",
    name: "Brightline Studio",
    setup_state,
    onboarding_step: 5,
    environment: "production",
  },
  businesses: [{ id: "b1", name: "Brightline Studio" }],
  permissions,
  roles: ["owner"],
});

export const OWNER = [
  "pi.read",
  "pi.inbox.reply",
  "pi.inbox.all",
  "pi.inbox.assign",
  "pi.inbox.notes",
  "pi.settings.manage",
  "pi.knowledge.manage",
  "pi.knowledge.publish",
  "pi.billing.read",
  "pi.billing.manage",
  "pi.memory.read",
  "pi.whatsapp.manage",
  "admin.members.read",
  "admin.members.manage",
  "pi.support.grant",
  "pi.customers.export",
  "customers.read",
  "pi.bookings.read",
  "pi.bookings.manage",
];
export const VIEWER = ["pi.read", "pi.inbox.all", "customers.read"];

const conversation = (id: string, name: string, mode = "ai", unread = 0) => ({
  id,
  customer_id: `c-${id}`,
  customer_name: name,
  customer_phone: "+15550001111",
  status: "open",
  mode,
  assigned_label: null,
  last_message_at: new Date().toISOString(),
  last_message_preview: "Hello, do you build online shops?",
  last_sender: "customer",
  unread_count: unread,
  language: "en",
  handoff_id: null,
  handoff_status: null,
  summary: "",
  pending_confirmation: false,
});

export async function mockApi(
  page: Page,
  permissions: string[],
  overrides: Record<string, unknown> = {},
) {
  const data: Record<string, unknown> = {
    "GET /auth/session": session(permissions),
    "GET /home": {
      name: "Brightline Studio",
      setup_state: "active",
      active: true,
      plan_reason: null,
      metrics: {
        conversations_7d: 2,
        pi_replies_7d: 1,
        enquiries_7d: 1,
        waiting_for_team: 1,
        awaiting_approval: 1,
        open_questions: 0,
        unread: 1,
        ai_unavailable_24h: 0,
      },
      next_actions: [
        {
          kind: "approvals",
          label: "1 replies to approve",
          href: "/inbox?filter=approvals",
        },
      ],
    },
    "GET /pi/conversations": {
      items: [
        conversation("1", "Sara", "ai", 1),
        conversation("2", "Bilal", "human"),
      ],
      total: 30,
      page: 1,
      page_size: 25,
    },
    "GET /pi/conversations/1/context": {
      conversation: conversation("1", "Sara", "ai", 0),
      service_brief: { requirements: { service: "Online shop" } },
    },
    "GET /pi/conversations/1/history": {
      items: [
        {
          id: "m1",
          conversation_id: "1",
          direction: "inbound",
          sender_type: "customer",
          message_type: "text",
          body: "Do you build online shops?",
          media: {},
          status: "received",
          error_code: null,
          created_at: new Date().toISOString(),
        },
        {
          id: "m2",
          conversation_id: "1",
          direction: "outbound",
          sender_type: "ai",
          message_type: "text",
          body: "Yes! What will you sell?",
          media: {},
          status: "pending_approval",
          error_code: null,
          created_at: new Date().toISOString(),
        },
      ],
      has_more: true,
      before: new Date().toISOString(),
      before_id: "m1",
    },
    "GET /pi/conversations/1/tags": [],
    "GET /pi/conversations/1/notes": [],
    "GET /pi/saved-replies": [],
    "GET /team": { members: [], roles: [] },
    ...overrides,
  };
  await page.route("**/api/v1/pi-app/**", async (route: Route) => {
    const url = new URL(route.request().url());
    const key = `${route.request().method()} ${url.pathname.replace("/api/v1/pi-app", "")}`;
    if (key in data) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(data[key]),
      });
    }
    if (route.request().method() !== "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "{}",
      });
    }
    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({
        error: { code: "NOT_FOUND", message: "Not found" },
      }),
    });
  });
}

export async function noHorizontalOverflow(page: Page) {
  return page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth,
  );
}
