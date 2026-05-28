import { defineConfig } from "@playwright/test";

const baseURL = "http://127.0.0.1:3001";
const mockApiURL = "http://127.0.0.1:4010";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.spec\.mjs$/,
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL,
    browserName: "chromium",
    channel: "chrome",
    headless: true,
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: "node e2e/support/mock-operator-api.mjs",
      url: `${mockApiURL}/__admin/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: "npm run dev -- --port 3001",
      url: baseURL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        NEXT_PUBLIC_API_BASE_URL: mockApiURL,
        NEXT_PUBLIC_TESTING_CONTROLS_ENABLED: "true",
      },
    },
  ],
});
