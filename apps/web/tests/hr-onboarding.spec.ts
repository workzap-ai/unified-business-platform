import { test, expect } from "@playwright/test";
import { signIn } from "./helpers";

// Sample-data mode: the demo adapter mirrors the onboarding API contract.
const PENDING = "/onboarding/demo-token-pending-00000000000000000000002";

test("HR reviews a submitted form and approves it into the directory", async ({
  page,
}) => {
  await signIn(page, "/hr/onboarding");
  await expect(page.getByRole("heading", { name: "Onboarding" })).toBeVisible();
  await page
    .getByRole("link", { name: /Hira Saleem/ })
    .first()
    .click();
  await expect(page.getByText("35201-0000000-2")).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await page.getByRole("button", { name: "Approve and add employee" }).click();
  await page.getByRole("link", { name: "Open employee" }).click();
  await expect(
    page.getByRole("heading", { name: "Hira Saleem", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Personal details")).toBeVisible();
});

test("HR creates a shareable link from the employees page", async ({
  page,
}) => {
  await signIn(page, "/hr/employees");
  await page.getByRole("link", { name: "Send onboarding link" }).click();
  await page.getByLabel("Employee name").fill("New Joiner");
  await page.getByRole("button", { name: "Create link" }).click();
  const link = page.getByRole("textbox", { name: "Onboarding link" });
  await expect(link).toHaveValue(/\/onboarding\/[A-Za-z0-9_-]{20,}$/);
  await expect(page.getByText(/can.t be shown\s+again/)).toBeVisible();
});

test("a new employee completes the public form on a phone", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page);
  await page.goto(PENDING);
  await expect(page.getByLabel("Full name as per CNIC")).toHaveValue(
    "Usman Tariq",
  );
  await page.getByRole("button", { name: "Submit details" }).click();
  await expect(page.getByText("Enter your father's name")).toBeVisible();

  await page.getByLabel("Father name").fill("Tariq Mehmood");
  await page.getByLabel("CNIC number").fill("3520212345671");
  await page.getByLabel("Male", { exact: true }).check();
  await page.getByLabel("Date of birth").fill("1996-05-20");
  await page.getByLabel("Date of joining").fill("2026-10-01");
  await page.getByLabel("Onsite").check();
  await page.getByLabel("Email").fill("usman@example.com");
  await page.getByLabel("Your contact number").fill("0300-1234567");
  await page
    .getByLabel("Current address with nearby landmark")
    .fill("House 5, near the main market, Lahore");
  await page.getByLabel("Emergency contact 1 — name").fill("Tariq (father)");
  await page.getByLabel("Emergency contact 1 — number").fill("0321-7654321");
  await page.getByLabel("Emergency contact 2 — name").fill("Asma (mother)");
  await page.getByLabel("Emergency contact 2 — number").fill("0333-1112223");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "Submit details" }).click();
  await expect(
    page.getByRole("heading", { name: /your details were received/i }),
  ).toBeVisible();
});

test("an unknown link explains what to do", async ({ page }) => {
  await page.goto("/onboarding/" + "x".repeat(43));
  await expect(
    page.getByText("This link isn't valid", { exact: true }),
  ).toBeVisible();
});
