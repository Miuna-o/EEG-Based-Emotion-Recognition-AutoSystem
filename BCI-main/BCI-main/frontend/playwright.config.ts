import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
const chromium =
  process.env.XINLAN_CHROMIUM ??
  "C:/Users/15611/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe";
export default defineConfig({
  testDir: "./tests",
  timeout: 60000,
  expect: { timeout: 15000 },
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: {
      executablePath: existsSync(chromium) ? chromium : undefined,
    },
  },
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: true,
  },
});
