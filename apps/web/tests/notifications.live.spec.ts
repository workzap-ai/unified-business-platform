import { test as base, expect } from "@playwright/test";
import type { Notification } from "../src/features/notifications/service";

// Exercise the live HTTP adapter with deterministic API responses. Database
// persistence, delivery audiences and bulk reads are covered by the API suite.
function notification(index: number, link: string | null = null): Notification {
  return {
    id: `notification-${index}`,
    kind: "system",
    severity: "info",
    title: `System alert ${index}`,
    body: "A notification to review",
    link,
    read: false,
    created_at: new Date().toISOString(),
  };
}

type Inbox = {
  items: Notification[];
  failReads: boolean;
  failRecent: boolean;
  permissions: string[];
  readRequests: (string[] | null)[];
};

const test = base.extend<{ inbox: Inbox }>({
  inbox: async ({ page }, provide) => {
    const inbox: Inbox = {
      items: [notification(1, "/notifications?opened=1"), notification(2)],
      failReads: false,
      failRecent: false,
      permissions: ["notifications.read"],
      readRequests: [],
    };
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/api/v1/**", async (route) => {
      const url = new URL(route.request().url());
      const path = url.pathname.replace("/api/v1/", "");
      const unread = inbox.items.filter((item) => !item.read).length;
      const json = (value: unknown) => route.fulfill({ json: value });
      const fail = () =>
        route.fulfill({
          status: 503,
          json: { error: { code: "SERVICE_UNAVAILABLE" } },
        });
      if (path === "auth/session")
        return json({
          user: {
            id: "user",
            email: "reader@example.com",
            display_name: "Reader",
          },
          tenant: { id: "tenant", name: "Notification tests" },
          environment: {
            id: "environment",
            name: "Production",
            kind: "production",
          },
          branch: null,
          permissions: inbox.permissions,
          roles: ["support"],
        });
      if (path === "tenants" || path === "environments") return json([]);
      if (path === "navigation")
        return json({
          sections: [
            {
              key: "admin",
              label: "Admin",
              customized: false,
              items: inbox.permissions.length
                ? [
                    {
                      key: "notifications",
                      label: "Notifications",
                      route: "/notifications",
                      icon: "bell",
                      type: "page",
                      section: "admin",
                      sort_order: 1,
                      badge: unread || null,
                      analytics_id: "nav.notifications",
                      keywords: [],
                      description: "Notifications",
                      children: [],
                    },
                  ]
                : [],
            },
          ],
        });
      if (path === "notifications/unread-count") return json({ unread });
      if (path === "notifications/read") {
        const { ids } = route.request().postDataJSON() as {
          ids: string[] | null;
        };
        inbox.readRequests.push(ids);
        if (inbox.failReads) return fail();
        for (const item of inbox.items)
          if (ids === null || ids.includes(item.id)) item.read = true;
        return route.fulfill({ status: 204 });
      }
      if (path === "notifications") {
        const pageSize = Number(url.searchParams.get("page_size"));
        const currentPage = Number(url.searchParams.get("page"));
        if (pageSize === 8 && inbox.failRecent) return fail();
        const items = inbox.items.filter(
          (item) =>
            url.searchParams.get("unread_only") !== "true" || !item.read,
        );
        return json({
          items: items.slice(
            (currentPage - 1) * pageSize,
            currentPage * pageSize,
          ),
          total: items.length,
          page: currentPage,
          page_size: pageSize,
        });
      }
      return route.fulfill({ status: 404, json: {} });
    });
    await provide(inbox);
    expect(errors).toEqual([]);
  },
});

test("opening a bell notification marks it read and refreshes both counts", async ({
  page,
  inbox,
}) => {
  await page.goto("/notifications");
  await page
    .getByRole("button", { name: "Notifications, 2 unread", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("link", { name: /System alert 1/ })
    .click();
  await expect(page).toHaveURL(/opened=1/);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Notifications, 1 unread", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Administration" }).getByRole("link"),
  ).toHaveText("Notifications1");
  expect(inbox.readRequests).toEqual([["notification-1"]]);
  await page.reload();
  await expect(
    page
      .getByRole("main")
      .getByRole("link", { name: /System alert 1/ })
      .getByLabel("Unread"),
  ).toHaveCount(0);
});

test("notifications without links can be read by keyboard and mark all updates the inbox", async ({
  page,
  inbox,
}) => {
  await page.goto("/notifications?view=unread");
  const alert = page.getByRole("button", {
    name: "Mark as read: System alert 2",
  });
  await alert.focus();
  await page.keyboard.press("Enter");
  await expect(alert).toHaveCount(0);
  expect(inbox.readRequests).toEqual([["notification-2"]]);
  await page
    .getByRole("button", { name: "Notifications, 1 unread", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Mark all read" })
    .click();
  await expect(
    page.getByRole("button", { name: "Notifications", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Administration" }).getByRole("link"),
  ).toHaveText("Notifications");
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("heading", { name: "You're all caught up" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Mark all read" }),
  ).toBeDisabled();
});

test("failed bulk reads display an error and can be retried", async ({
  page,
  inbox,
}) => {
  inbox.failReads = true;
  await page.goto("/notifications");
  await page
    .getByRole("button", { name: "Notifications, 2 unread", exact: true })
    .click();
  const markAll = page
    .getByRole("dialog")
    .getByRole("button", { name: "Mark all read" });
  await markAll.click();
  await expect(page.getByText(/temporarily unavailable/)).toBeVisible();
  expect(inbox.items.every((item) => !item.read)).toBe(true);
  inbox.failReads = false;
  await markAll.click();
  await expect(
    page.getByRole("button", { name: "Notifications", exact: true }),
  ).toBeVisible();
});

test("the bell offers a retry when recent notifications fail to load", async ({
  page,
  inbox,
}) => {
  inbox.failRecent = true;
  await page.goto("/notifications");
  await page
    .getByRole("button", { name: "Notifications, 2 unread", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByText("Notifications could not be loaded"),
  ).toBeVisible();
  inbox.failRecent = false;
  await dialog.getByRole("button", { name: /try again|retry/i }).click();
  await expect(
    dialog.getByRole("link", { name: /System alert 1/ }),
  ).toBeVisible();
});

test("reading the last item on an unread page returns to the remaining notifications", async ({
  page,
  inbox,
}) => {
  inbox.items = Array.from({ length: 26 }, (_, index) =>
    notification(index + 1),
  );
  await page.goto("/notifications?view=unread&page=2");
  await page
    .getByRole("button", { name: "Mark as read: System alert 26" })
    .click();
  await expect(page).toHaveURL(/\/notifications\?view=unread$/);
  await expect(
    page.getByRole("button", {
      name: "Mark as read: System alert 1",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText("Page 1 of 1")).toBeVisible();
  await page
    .getByRole("main")
    .getByRole("button", { name: "Mark all read" })
    .click();
  await expect(
    page.getByRole("heading", { name: "You're all caught up" }),
  ).toBeVisible();
});

test("new notifications refresh the open bell, inbox and sidebar", async ({
  page,
  inbox,
}) => {
  await page.clock.install();
  await page.goto("/notifications");
  await page
    .getByRole("button", { name: "Notifications, 2 unread", exact: true })
    .click();
  await expect(
    page.getByRole("dialog").getByText("System alert 2"),
  ).toBeVisible();
  inbox.items.unshift(notification(3));
  await page.clock.fastForward(60_000);
  await expect(
    page.getByRole("button", { name: "Notifications, 3 unread", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("dialog").getByText("System alert 3"),
  ).toBeVisible();
  await expect(
    page.getByRole("main").getByText("System alert 3"),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Administration" }).getByRole("link"),
  ).toHaveText("Notifications3");
});

test("a notification without a link can be read from the bell on a phone", async ({
  page,
  inbox,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/notifications?page=Infinity");
  await page
    .getByRole("button", { name: "Notifications, 2 unread", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByRole("button", { name: "Mark as read: System alert 2" })
    .click();
  await expect(dialog.getByText("System alert 2")).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Mark as read: System alert 2" }),
  ).toHaveCount(0);
  expect(inbox.readRequests).toEqual([["notification-2"]]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("users without notification permission see neither the bell nor the inbox", async ({
  page,
  inbox,
}) => {
  inbox.permissions = [];
  await page.goto("/notifications");
  await expect(
    page.getByRole("heading", { name: /have access/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /^Notifications/ }),
  ).toHaveCount(0);
  expect(inbox.readRequests).toEqual([]);
});
