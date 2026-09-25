import { defineConfig, devices } from "@playwright/test";
const baseURL = process.env.LIVE_BASE_URL ?? "http://127.0.0.1:3100";
export default defineConfig({
  testDir: "./tests",
  testMatch: [
    "live.spec.ts",
    "auth.live.spec.ts",
    "integrations.live.spec.ts",
    "notifications.live.spec.ts",
  ],
  workers: 1,
  timeout: 120_000,
  use: { baseURL, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: process.env.LIVE_BASE_URL
    ? undefined
    : {
        command: "npm run start",
        env: { PORT: "3100", HOSTNAME: "127.0.0.1" },
        url: baseURL,
        reuseExistingServer: false,
      },
});
