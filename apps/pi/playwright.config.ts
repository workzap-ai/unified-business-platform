import { defineConfig, devices } from "@playwright/test";

// Browser journeys run against a production build of the Pi app. By default the API is
// mocked at the network layer (tests/support.ts) so layout, states and permissions can be
// checked without a backend; set PI_LIVE_API=1 with a running API for live journeys.
export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:3210", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run start",
    env: { PORT: "3210", HOSTNAME: "127.0.0.1" },
    url: "http://127.0.0.1:3210/sign-in",
    reuseExistingServer: false,
  },
});
