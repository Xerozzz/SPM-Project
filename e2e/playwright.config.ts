import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests run against the stack started by `docker compose up`, at the same
 * URL a marker would open in a browser. Playwright starts no server of its own: if the
 * compose stack is not up, the tests fail loudly rather than testing something else.
 */
export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [['html', { open: 'never' }], ['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
