import { test as base, expect } from '@playwright/test';
import { currentUser, loginAs, logout } from '../helpers/auth';

const controlURL =
  process.env.E2E_CONTROL_URL ??
  `http://127.0.0.1:${process.env.E2E_CONTROL_PORT ?? '18000'}`;

type AppFixtures = {
  loginAsAdmin: () => Promise<void>;
  loginAsProfessor: () => Promise<void>;
  loginAsStudent: () => Promise<void>;
  logoutCurrentUser: () => Promise<void>;
  fetchCurrentUser: () => ReturnType<typeof currentUser>;
};

export const test = base.extend<AppFixtures>({
  page: async ({ page }, use, testInfo) => {
    const testId = `${testInfo.workerIndex}-${testInfo.parallelIndex}-${testInfo.testId}-${testInfo.retry}`;
    await page.context().addCookies([
      {
        name: 'e2e_test_id',
        value: encodeURIComponent(testId),
        url: 'http://127.0.0.1:5173',
        sameSite: 'Lax'
      }
    ]);
    const response = await page.context().request.post(
      `${controlURL}/__test/reset`
    );
    expect(response.ok()).toBeTruthy();
    await use(page);
  },
  request: async ({ page }, use) => {
    await use(page.context().request);
  },
  loginAsAdmin: async ({ page }, use) => {
    await use(() => loginAs(page, 'admin'));
  },

  loginAsProfessor: async ({ page }, use) => {
    await use(() => loginAs(page, 'professor'));
  },

  loginAsStudent: async ({ page }, use) => {
    await use(() => loginAs(page, 'student'));
  },

  logoutCurrentUser: async ({ page }, use) => {
    await use(() => logout(page));
  },

  fetchCurrentUser: async ({ page }, use) => {
    await use(() => currentUser(page.context().request));
  }
});

export { expect };
