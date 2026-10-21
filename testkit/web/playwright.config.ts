import path from "node:path";
import { defineConfig, devices, type Project } from "@playwright/test";
import { config, REPORTS_DIR } from "./src/config";

const deviceFor: Record<string, (typeof devices)[string]> = {
  chromium: devices["Desktop Chrome"],
  firefox: devices["Desktop Firefox"],
  webkit: devices["Desktop Safari"],
};

const browserProjects: Project[] = config.web.browsers.map((name) => ({
  name,
  use: {
    ...deviceFor[name],
    // Navegador já instalado no sistema (ex.: imagens Nix/Alpine): TESTKIT_CHROMIUM_PATH=/caminho/chromium
    ...(name === "chromium" && process.env.TESTKIT_CHROMIUM_PATH ? { launchOptions: { executablePath: process.env.TESTKIT_CHROMIUM_PATH } } : {}),
  },
  dependencies: ["setup"],
  // Auditorias pesadas e independentes de motor rodam só no Chromium.
  testIgnore: name === "chromium" ? [] : [/performance\.spec\.ts/, /crawl\.spec\.ts/, /security\.spec\.ts/],
}));

export default defineConfig({
  testDir: "./tests",
  outputDir: path.join(REPORTS_DIR, "playwright-artifacts"),
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? config.web.retries : 0,
  workers: process.env.CI ? config.web.workers : undefined,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  reporter: [
    ["list"],
    ["html", { outputFolder: path.join(REPORTS_DIR, "playwright-html"), open: "never" }],
    ["junit", { outputFile: path.join(REPORTS_DIR, "playwright-junit.xml") }],
    ...(process.env.GITHUB_ACTIONS ? ([["github"]] as const) : []),
  ],
  use: {
    baseURL: config.web.baseUrl,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    ignoreHTTPSErrors: !!process.env.TESTKIT_IGNORE_HTTPS_ERRORS,
    locale: process.env.TESTKIT_LOCALE || "pt-BR",
  },
  projects: [{
      name: "setup",
      testMatch: /setup\/.*\.setup\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        ...(process.env.TESTKIT_CHROMIUM_PATH ? { launchOptions: { executablePath: process.env.TESTKIT_CHROMIUM_PATH } } : {}),
      },
    }, ...browserProjects],
});
