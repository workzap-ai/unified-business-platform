import { z } from "zod";
import { apiRequest, pageSchema, type Page } from "@/services/api-client";
import { demoDelay, select } from "@/lib/data-mode";
import { demoCollection, paginate } from "@/demo/store";
import { daysAgo } from "@/demo/random";

export const notificationSchema = z.object({
  id: z.string(),
  kind: z.string(),
  severity: z.enum(["info", "warning", "critical"]),
  title: z.string(),
  body: z.string(),
  link: z.string().nullable(),
  read: z.boolean(),
  created_at: z.string(),
});
export type Notification = z.infer<typeof notificationSchema>;

export interface NotificationsService {
  list(params: {
    page?: number;
    pageSize?: number;
    unreadOnly?: boolean;
  }): Promise<Page<Notification>>;
  unreadCount(): Promise<number>;
  markRead(ids: string[] | null): Promise<void>;
}

const live: NotificationsService = {
  list: ({ page = 1, pageSize = 25, unreadOnly = false }) =>
    apiRequest("GET", "/notifications", pageSchema(notificationSchema), {
      query: { page, page_size: pageSize, unread_only: unreadOnly },
    }),
  unreadCount: async () =>
    (
      await apiRequest(
        "GET",
        "/notifications/unread-count",
        z.object({ unread: z.number() }),
      )
    ).unread,
  markRead: (ids) =>
    apiRequest("POST", "/notifications/read", null, { body: { ids } }),
};

type Seed = Omit<Notification, "id" | "created_at"> & { ago: number };

const COMMERCE: Seed[] = [
  {
    kind: "handoff",
    severity: "warning",
    title: "Handoff: refund question from Bilal Qureshi",
    body: "PI escalated a complaint about a delayed delivery.",
    link: "/pi/handoffs/open",
    read: false,
    ago: 0.02,
  },
  {
    kind: "inventory",
    severity: "warning",
    title: "Low stock: TEA-GRN-250",
    body: "Jasmine Green Tea 250g has 3 available (threshold 10).",
    link: "/inventory/stock?low_only=true",
    read: false,
    ago: 0.08,
  },
  {
    kind: "pi",
    severity: "info",
    title: "PI confirmed order ORD-000418",
    body: "Customer confirmed 2 × Ceramic Pour-Over Kit on WhatsApp.",
    link: "/orders",
    read: false,
    ago: 0.3,
  },
  {
    kind: "billing",
    severity: "critical",
    title: "3 invoices are more than 30 days overdue",
    body: "PKR 186,400 outstanding across Harbor Foods, Crescent Café and Lumen Retail.",
    link: "/billing/invoices?overdue=true",
    read: false,
    ago: 0.9,
  },
  {
    kind: "handoff",
    severity: "warning",
    title: "Handoff: custom bulk pricing request",
    body: "Customer asked for wholesale pricing that needs approval.",
    link: "/pi/handoffs/open",
    read: true,
    ago: 1.4,
  },
  {
    kind: "pi",
    severity: "warning",
    title: "AI provider fallback used 6 times today",
    body: "Primary provider hit a rate limit; replies continued through the fallback provider.",
    link: "/pi/analytics/fallbacks",
    read: true,
    ago: 1.7,
  },
  {
    kind: "quotes",
    severity: "info",
    title: "Quote QUO-000092 awaits approval",
    body: "Discount above policy threshold (15%).",
    link: "/quotes/approvals",
    read: false,
    ago: 2.2,
  },
  {
    kind: "inventory",
    severity: "critical",
    title: "Out of stock: MUG-STN-BLK",
    body: "Stoneware Mug — Black has 0 available.",
    link: "/inventory/stock?low_only=true",
    read: true,
    ago: 3.1,
  },
  {
    kind: "system",
    severity: "info",
    title: "Staging environment created",
    body: "Omar Siddiqui created the Staging environment.",
    link: "/settings/environments",
    read: true,
    ago: 5,
  },
  {
    kind: "billing",
    severity: "info",
    title: "Payment received: INV-000311",
    body: "PKR 42,500 by bank transfer from Harbor Foods.",
    link: "/billing/payments",
    read: true,
    ago: 6,
  },
  {
    kind: "pi",
    severity: "info",
    title: "Knowledge document processed",
    body: "“Returns & Exchanges Policy” is ready (14 passages).",
    link: "/pi/knowledge/documents",
    read: true,
    ago: 8,
  },
  {
    kind: "system",
    severity: "info",
    title: "New member joined",
    body: "Sana Malik joined as Support.",
    link: "/settings/members",
    read: true,
    ago: 12,
  },
];

const SERVICES: Seed[] = [
  {
    kind: "handoff",
    severity: "warning",
    title: "Handoff: website redesign budget",
    body: "PI collected requirements; pricing needs a human.",
    link: "/pi/handoffs/open",
    read: false,
    ago: 0.2,
  },
  {
    kind: "quotes",
    severity: "info",
    title: "Quote QUO-000014 awaits approval",
    body: "Quotes drafted by PI always need approval.",
    link: "/quotes/approvals",
    read: false,
    ago: 1.1,
  },
];

const demoNotifications = demoCollection<Notification[]>(
  "notifications",
  (profile) => {
    const seeds =
      profile.kind === "commerce"
        ? COMMERCE
        : profile.kind === "services"
          ? SERVICES
          : [];
    return seeds.map(({ ago, ...rest }, index) => ({
      ...rest,
      id: `ntf-${profile.environmentId}-${index + 1}`,
      created_at: daysAgo(ago),
    }));
  },
);

const demo: NotificationsService = {
  async list({ page = 1, pageSize = 25, unreadOnly = false }) {
    await demoDelay();
    const items = demoNotifications().filter((n) => !unreadOnly || !n.read);
    return paginate(
      items.map((n) => ({ ...n })),
      page,
      pageSize,
    );
  },
  async unreadCount() {
    await demoDelay(60);
    return demoNotifications().filter((n) => !n.read).length;
  },
  async markRead(ids) {
    await demoDelay(100);
    for (const n of demoNotifications())
      if (!ids || ids.includes(n.id)) n.read = true;
  },
};

export const notificationsService = select<NotificationsService>({
  demo,
  live,
});
export { demoNotifications };
