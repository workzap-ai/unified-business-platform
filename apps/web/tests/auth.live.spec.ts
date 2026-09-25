import { expect, test } from "@playwright/test";

test("registration, reload, duplicate email and sign-in use the live backend", async ({
  page,
  baseURL,
}) => {
  const stamp = Date.now();
  const email = `registration-${stamp}@example.com`;
  const workspace = `Registration check ${stamp}`;
  const password = "Local-registration-check-2026!";
  const failures: string[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/api/v1/") && response.status() >= 500) {
      failures.push(`${response.status()} ${new URL(response.url()).pathname}`);
    }
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await page.goto("/register");
  await page.getByLabel("Your name").fill("Registration Check");
  await page.getByLabel("Business name").fill(workspace);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  const registered = page.waitForResponse(
    (response) =>
      response.url().endsWith("/auth/register") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Create workspace", exact: true })
    .click();
  expect((await registered).status()).toBe(201);
  await expect(
    page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", {
      name: `Workspace: ${workspace}. Switch workspace`,
    }),
  ).toBeVisible();
  const session = await page.request.get("/api/v1/auth/session");
  expect(session.status()).toBe(200);
  expect((await session.json()).user.email).toBe(email);
  const cookies = await page.context().cookies();
  expect(
    cookies.find((cookie) => cookie.name === "platform_session")?.httpOnly,
  ).toBe(true);
  const csrf = cookies.find((cookie) => cookie.name === "platform_csrf")!.value;
  expect(
    (
      await page.request.post("/api/v1/auth/logout", {
        headers: { "x-csrf-token": csrf, origin: new URL(baseURL!).origin },
      })
    ).status(),
  ).toBe(204);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();

  await page.goto("/register");
  await page.getByLabel("Your name").fill("Registration Check");
  await page.getByLabel("Business name").fill(workspace);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  const duplicate = page.waitForResponse(
    (response) =>
      response.url().endsWith("/auth/register") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Create workspace", exact: true })
    .click();
  expect((await duplicate).status()).toBe(409);
  await expect(
    page.getByText("The service had a problem. Please try again shortly."),
  ).toHaveCount(0);

  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: `Workspace: ${workspace}. Switch workspace`,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ }),
  ).toBeVisible();
  expect(failures).toEqual([]);
});
