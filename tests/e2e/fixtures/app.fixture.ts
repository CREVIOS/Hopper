import { test as base, expect } from '@playwright/test';
import { currentUser, loginAs, logout } from '../helpers/auth';

type AppFixtures = {
  loginAsAdmin: () => Promise<void>;
  loginAsStudent: () => Promise<void>;
  logoutCurrentUser: () => Promise<void>;
  fetchCurrentUser: () => ReturnType<typeof currentUser>;
};

export const test = base.extend<AppFixtures>({
  page: async ({ page, request }, use) => {
    const response = await request.post(
      `${process.env.E2E_CONTROL_URL ?? 'http://127.0.0.1:8000'}/__test/reset`
    );
    expect(response.ok()).toBeTruthy();
    await use(page);
  },
  loginAsAdmin: async ({ page }, use) => {
    await use(() => loginAs(page, 'admin'));
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
