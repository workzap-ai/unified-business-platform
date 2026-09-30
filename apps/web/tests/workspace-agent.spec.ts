import { test, expect } from "@playwright/test";
import { signIn } from "./helpers";

test("workspace assistant is available in demo but does not simulate real writes", async ({
  page,
}) => {
  await signIn(page, "/workspace-agent");
  await expect(
    page.getByRole("heading", { name: "Pi Agent Beta" }),
  ).toBeVisible();
  await expect(page.getByText("Ready for your live workspace")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Download 10-employee CSV example" }),
  ).toHaveAttribute("href", "/templates/agent-employees-10.csv");
  await expect(
    page.getByRole("button", { name: "Confirm changes" }),
  ).toHaveCount(0);
});
