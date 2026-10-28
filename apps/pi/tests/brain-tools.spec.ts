import { expect, test } from "@playwright/test";

import { mockApi, noHorizontalOverflow, OWNER } from "./support";

// Brain tools for staff: annotations in the thread, review queue, moderation and erasure,
// brain health, documents queue, and the pi mode on the Agents page. API doubles only.

const STAFF = [...OWNER, "pi.handoffs.manage", "sales.read", "quotes.write"];

const message = (id: string, over: Record<string, unknown>) => ({
  id,
  conversation_id: "1",
  direction: "outbound",
  sender_type: "ai",
  message_type: "text",
  body: "",
  media: {},
  status: "sent",
  error_code: null,
  created_at: new Date().toISOString(),
  ...over,
});

test("a pi message shows what pi understood, collapsed until opened", async ({
  page,
}) => {
  await mockApi(page, STAFF, {
    "GET /pi/conversations/1/history": {
      items: [
        message("m1", {
          body: "Aap ke stock ka hisaab kaun rakhta hai?",
          understood: {
            move: "summarise",
            label: "Noted",
            reason: "the owner named a second problem",
            problems: [
              { number: 2, title: "Stock count is wrong", category: "stock" },
            ],
            hypotheses: [
              { text: "Counts are not written down", confidence: "medium" },
            ],
            offer: {
              rule: "R1",
              allowed: false,
              blocked_reason: "still listening",
            },
            box_state: "collecting",
          },
        }),
        message("m2", { body: "Plain reply with nothing stored" }),
      ],
      has_more: false,
      before: null,
      before_id: null,
    },
  });
  await page.goto("/inbox?conversation=1");
  const notes = page.getByTestId("message-notes");
  await expect(notes).toHaveCount(1);
  await expect(notes).toContainText("What pi understood");
  await expect(notes).toContainText("1 problem noted");
  await expect(page.getByText("P2: Stock count is wrong")).toBeHidden();
  await notes.getByText("What pi understood").click();
  await expect(page.getByText("P2: Stock count is wrong")).toBeVisible();
  await expect(page.getByText(/not confirmed by the owner/)).toBeVisible();
  await expect(page.getByText(/No offer yet \(rule R1\)/)).toBeVisible();
  await expect(page.getByText(/Box collecting/)).toBeVisible();
});

test("the staff review link opens the in-app review when no staff app address is set", async ({
  page,
}) => {
  await mockApi(page, STAFF, {});
  await page.goto("/inbox?conversation=1");
  const link = page.getByRole("link", { name: "Staff review" });
  await expect(link).toHaveAttribute("href", "/brain/review?c=1");
});

const alerts = [
  {
    level: "red",
    key: "churn_risk",
    label: "Churn risk",
    detail: "The owner said they may look elsewhere.",
  },
];

const attention = {
  items: [
    {
      conversation_id: "1",
      customer_ref: "1a2b3c4d",
      phone: "•••• 1111",
      language: "ur",
      mode: "ai",
      unread_count: 1,
      last_message_at: new Date().toISOString(),
      alerts,
    },
  ],
  total: 1,
};

const review = (flow_state: string) => ({
  conversation: {
    id: "1",
    customer_ref: "1a2b3c4d",
    phone: "•••• 1111",
    language: "ur",
    mode: "ai",
    status: "open",
    flow_state,
    last_message_at: new Date().toISOString(),
  },
  map: {
    version: 2,
    nodes: [
      {
        id: "P1",
        title: "Orders get lost",
        category_label: "Orders",
        status: "open",
      },
    ],
  },
  thinking: { posture: "steady", hypotheses: [] },
  diagnosis: null,
  ideas: { given_for_business: 2, per_business_cap: 8, business_remaining: 6 },
  handover: {
    handoff: {
      status: "open",
      origin_text: "The owner asked for a person",
      summary: "",
      priority: "normal",
    },
  },
  box: { box: { state: "collecting", version: 1, reviewer: null }, offers: [] },
  labels: { alerts },
});

test("staff see the review queue, then erase a person's data after typing the confirmation", async ({
  page,
}) => {
  let erased = false;
  await mockApi(page, STAFF, {
    "GET /pi/review/attention": attention,
    "GET /pi/review/conversations/1": review("S1_LISTENING"),
    "GET /pi/conversations/1/context": {
      conversation: { id: "1", customer_id: "c-1", customer_name: "Sara" },
    },
    "POST /pi/brain-erasure/c-1": {
      removed: { problems: 3, memories: 2, messages_cleared: 14, links: 0 },
      kept: { documents: 1, payments: 0 },
      conversations: 1,
    },
  });
  page.on("request", (r) => {
    if (r.url().includes("/pi/brain-erasure/c-1")) erased = true;
  });
  await page.goto("/brain/review");
  await expect(page.getByText("Churn risk").first()).toBeVisible();
  await page.getByRole("link", { name: /1111/ }).click();
  await expect(page.getByText("The owner asked for a person")).toBeVisible();
  await expect(page.getByText("P1: Orders get lost")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Put it back to listening" }),
  ).toHaveCount(0);

  await page.getByRole("button", { name: "Erase their data" }).click();
  const dialog = page.getByRole("dialog");
  const erase = dialog.getByRole("button", { name: "Erase for good" });
  await expect(erase).toBeDisabled();
  await dialog.getByLabel(/Type "erase 1a2b3c4d"/).fill("erase");
  await expect(erase).toBeDisabled();
  expect(erased).toBe(false);
  await dialog.getByLabel(/Type "erase 1a2b3c4d"/).fill("erase 1a2b3c4d");
  await expect(erase).toBeEnabled();
  await erase.click();
  const result = page.getByTestId("erase-result");
  await expect(result).toContainText("3 problems");
  await expect(result).toContainText("14 messages (the words are gone)");
  await expect(result).toContainText("1 document and 0 payments");
});

test("a chat pi stopped answering can be put back to listening", async ({
  page,
}) => {
  let unblocked = false;
  await mockApi(page, STAFF, {
    "GET /pi/review/attention": attention,
    "GET /pi/review/conversations/1": review("X_BLOCKED"),
    "POST /pi/brain-moderation/1/unblock": {
      id: "1",
      flow_state: "S1_LISTENING",
      from: "X_BLOCKED",
    },
  });
  page.on("request", (r) => {
    if (r.url().includes("/unblock")) unblocked = true;
  });
  await page.goto("/brain/review?c=1");
  await expect(page.getByText("pi stopped answering this chat")).toBeVisible();
  await page.getByRole("button", { name: "Put it back to listening" }).click();
  await expect(
    page.getByText("pi is listening to this chat again"),
  ).toBeVisible();
  expect(unblocked).toBe(true);
});

test("without the capability the review queue explains instead of loading", async ({
  page,
}) => {
  await mockApi(page, OWNER, {});
  await page.goto("/brain/review");
  await expect(page.getByText("You can't review conversations")).toBeVisible();
});

test("brain health shows the mode, the freeze state and the numbers", async ({
  page,
}) => {
  await mockApi(page, STAFF, {
    "GET /pi/brain-health": {
      days: 7,
      pi_mode: "brain",
      learning_frozen: true,
      metrics: {
        scored: 40,
        average_reward: 0.4,
        rule_break_rate: 0,
        first_time_confirmation_rate: 0.5,
        confusion_rate: 0.05,
        correction_rate: 0.1,
        opt_out_rate: 0,
        complaint_rate: 0,
      },
      learning: {
        changes_promoted: 3,
        changes_rolled_back: 1,
        questions_with_a_proven_best: 0.25,
        waiting_for_review: 2,
        packs_by_status: {},
      },
      settings: {
        ideas_per_problem: { value: 2, default: 2, low: 1, high: 3 },
      },
    },
  });
  await page.goto("/brain/health");
  await expect(page.getByTestId("pi-mode")).toHaveText("Brain mode");
  await expect(page.getByText("Learning is frozen")).toBeVisible();
  await expect(page.getByText("Rule breaks (must be 0)")).toBeVisible();
  await expect(page.getByText("2 items wait for a reviewer.")).toBeVisible();
  expect(await noHorizontalOverflow(page)).toBe(true);
});

test("the documents queue lists drafts first and approves on the reviewer's click", async ({
  page,
}) => {
  const doc = (id: string, ref: string, status: string) => ({
    id,
    ref,
    kind: "solution",
    version: 1,
    status,
    total: null,
    currency: null,
    language: "en",
    drafted_by: "pi",
    approved_by: null,
    created_at: new Date().toISOString(),
    blockers: [],
  });
  let approved = false;
  await mockApi(page, STAFF, {
    "GET /pi/brain-documents": {
      items: [doc("d1", "SD-1", "sent"), doc("d2", "SD-2", "draft")],
    },
    "POST /pi/brain-documents/d2/approve": doc("d2", "SD-2", "approved"),
  });
  page.on("request", (r) => {
    if (r.url().endsWith("/d2/approve")) approved = true;
  });
  await page.goto("/brain/documents");
  const items = page.getByRole("main").getByRole("listitem");
  await expect(items.first()).toContainText("SD-2");
  await expect(
    items.nth(1).getByRole("button", { name: "Approve" }),
  ).toHaveCount(0);
  await items.first().getByRole("button", { name: "Approve" }).click();
  await expect.poll(() => approved).toBe(true);
});

const agent = (key: string, mode: string) => ({
  id: `a-${key}`,
  key,
  name: key,
  role: "",
  pi_mode: mode,
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

test("the Agents page shows the mode the API reports, without reading settings", async ({
  page,
}) => {
  await mockApi(page, [...STAFF, "pi.agents.manage"], {
    "GET /pi/agents": [agent("router", "brain"), agent("requirement", "brain")],
  });
  await page.goto("/my-pi/agents");
  await expect(page.getByTestId("pi-mode")).toContainText("Brain mode");
  await expect(
    page.getByRole("link", { name: /Brain review, health and documents/ }),
  ).toHaveAttribute("href", "/brain/review");
});

test("a legacy workspace shows legacy mode on the Agents page", async ({
  page,
}) => {
  await mockApi(page, [...OWNER, "pi.agents.manage"], {
    "GET /pi/agents": [agent("router", "legacy")],
  });
  await page.goto("/my-pi/agents");
  await expect(page.getByTestId("pi-mode")).toContainText("Legacy mode");
});
