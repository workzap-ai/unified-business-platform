import { expect, test } from "@playwright/test";

import { mockApi, OWNER } from "./support";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

const message = (
  id: string,
  over: Record<string, unknown>,
): Record<string, unknown> => ({
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

function history(items: Record<string, unknown>[]) {
  return {
    "GET /pi/conversations/1/history": {
      items,
      has_more: false,
      before: null,
      before_id: null,
    },
  };
}

test("a thread shows pi's map picture, PDF and buttons, and a customer's reading", async ({
  page,
}) => {
  await page.route("https://signed.example.com/map.png", (route) =>
    route.fulfill({ status: 200, contentType: "image/png", body: PNG }),
  );
  await mockApi(
    page,
    OWNER,
    history([
      message("m1", {
        body: "Here is the map of what you told me.",
        media: {
          image: "https://signed.example.com/map.png",
          visual: "map",
          alt: "Problem map: orders get lost",
          map_version: 2,
          buttons: ["Looks right", "Change something"],
        },
        card: { kind: "map", image: "https://signed.example.com/map.png" },
      }),
      message("m2", {
        media: {
          document: {
            link: "https://signed.example.com/doc.pdf",
            filename: "solution.pdf",
          },
        },
      }),
      message("m3", {
        direction: "inbound",
        sender_type: "customer",
        message_type: "image",
        body: "A messy shelf",
        media: { description: "A shelf with unlabelled boxes" },
        status: "processed",
      }),
      message("m4", {
        direction: "inbound",
        sender_type: "customer",
        message_type: "text",
        body: "مجھے مدد چاہیے",
      }),
    ]),
  );
  await page.goto("/inbox?conversation=1");
  const picture = page.getByTestId("sent-picture");
  await expect(picture).toContainText("Problem map");
  await expect(picture).toContainText("Problem map: orders get lost");
  await expect(picture.getByRole("img")).toBeVisible();
  const pdf = page.getByRole("link", { name: "solution.pdf" });
  await expect(pdf).toHaveAttribute("target", "_blank");
  await expect(pdf).toHaveAttribute("rel", /noopener/);
  const buttons = page.getByTestId("sent-buttons");
  await expect(buttons).toContainText("Buttons sent");
  await expect(buttons).toContainText("Looks right");
  await expect(page.getByText("pi read this image as:")).toBeVisible();
  await expect(page.getByText("A shelf with unlabelled boxes")).toBeVisible();
  await expect(page.getByRole("button", { name: "Show image" })).toBeVisible();
  await expect(page.getByText("مجھے مدد چاہیے")).toHaveAttribute("dir", "auto");
});

test("an expired picture shows a placeholder, never a broken image", async ({
  page,
}) => {
  await page.route("https://signed.example.com/old.png", (route) =>
    route.fulfill({ status: 403, body: "expired" }),
  );
  await mockApi(
    page,
    OWNER,
    history([
      message("m1", {
        media: {
          image: "https://signed.example.com/old.png",
          visual: "board",
          alt: "Your board",
        },
      }),
    ]),
  );
  await page.goto("/inbox?conversation=1");
  await expect(page.getByText("Picture expired")).toBeVisible();
  await expect(page.getByTestId("sent-picture")).toContainText("Board");
});
