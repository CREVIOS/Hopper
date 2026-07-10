import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:5173';
const enableCrossBrowser = /^(1|true|yes)$/i.test(process.env.E2E_CROSS_BROWSER ?? '');

export default defineConfig({
  testDir: './specs',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI
    ? [['list'], ['html', { open: 'never' }]]
    : [['list'], ['html', { open: 'never' }]],
  timeout: 60_000,
  expect: {
    timeout: 10_000
  },
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure'
  },
  outputDir: './test-results',
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    },
    ...(enableCrossBrowser
      ? [
          {
            name: 'firefox',
            use: { ...devices['Desktop Firefox'] }
          },
          {
            name: 'webkit',
            use: { ...devices['Desktop Safari'] }
          }
        ]
      : [])
  ],
  webServer: {
    command: 'node ./node_modules/vite/bin/vite.js dev --host 127.0.0.1 --port 5173',
    cwd: '../../frontend',
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      ...process.env,
      API_PROXY_TARGET: process.env.API_PROXY_TARGET ?? 'https://hopper.farefin.com',
      API_PROXY_STRIP_PREFIX: process.env.API_PROXY_STRIP_PREFIX ?? 'false',
      API_PROXY_SECURE: process.env.API_PROXY_SECURE ?? 'true',
      API_PROXY_ORIGIN: process.env.API_PROXY_ORIGIN ?? 'https://hopper.farefin.com',
      API_INTERNAL_URL: process.env.API_INTERNAL_URL ?? 'https://hopper.farefin.com/api',
      KEYCLOAK_EXTERNAL_URL:
        process.env.KEYCLOAK_EXTERNAL_URL ?? 'https://hopper.farefin.com',
      KEYCLOAK_REALM: process.env.KEYCLOAK_REALM ?? 'hopper',
      KEYCLOAK_CLIENT_ID: process.env.KEYCLOAK_CLIENT_ID ?? 'hopper-api'
    }
  }
});
