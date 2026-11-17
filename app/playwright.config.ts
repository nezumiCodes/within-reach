import { defineConfig, devices } from '@playwright/test'

// LIVE_URL=https://withinreach.vasnik.net runs the same tests against the deployed site.
const liveUrl = process.env.LIVE_URL
const baseURL = liveUrl ?? 'http://localhost:4173'

export default defineConfig({
  testDir: './tests/e2e',
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: { baseURL, trace: 'retain-on-failure' },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
    // Edge is the main target on NHS and council devices (NFR-08). Needs `playwright install msedge`.
    ...(process.env.PW_EDGE
      ? [{ name: 'edge', use: { ...devices['Desktop Edge'], channel: 'msedge' } }]
      : []),
  ],
  webServer: liveUrl
    ? undefined
    : {
        command: 'npm run build && npm run preview -- --port 4173 --strictPort',
        url: baseURL,
        reuseExistingServer: !process.env.CI,
      },
})
