import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testIgnore: ["**/live.spec.ts", "**/auth.live.spec.ts"],
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:3100", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run start",
    env: { PORT: "3100", HOSTNAME: "127.0.0.1" },
    url: "http://127.0.0.1:3100",
    reuseExistingServer: false,
  },
});
