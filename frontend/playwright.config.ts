import { defineConfig, devices } from '@playwright/test';

/**
 * Lumen Frontend — Playwright E2E Test Configuration
 *
 * Run tests:
 *   npx playwright test
 *
 * UI mode:
 *   npx playwright test --ui
 *
 * Report:
 *   npx playwright show-report
 *
 * Prerequisites:
 *   1. Start Lumen frontend: npm run dev  (http://localhost:5173)
 *   2. Optionally start backend: cd ../backend && uvicorn app.main:socket_app
 *
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: './tests/e2e',

  // Run all tests in a file sequentially — avoids race conditions on shared state
  fullyParallel: false,

  // Fail the build on CI if any test.only remains
  forbidOnly: !!process.env.CI,

  // Retry once on CI; no retries locally
  retries: process.env.CI ? 1 : 0,

  // Single worker in CI to stay deterministic; local dev can run multiple
  workers: process.env.CI ? 1 : undefined,

  // HTML report for local inspection; list output in CI
  reporter: process.env.CI ? 'list' : 'html',

  use: {
    // Base URL for all page.goto('/') calls
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5173',

    // Collect trace on first retry to aid debugging
    trace: 'on-first-retry',

    // Screenshot on failure
    screenshot: 'only-on-failure',

    // Viewport
    viewport: { width: 1280, height: 800 },

    // Reasonable action timeout
    actionTimeout: 10_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
  ],

  // Automatically start the Vite dev server before running tests
  // Comment out if you prefer to start it manually
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
