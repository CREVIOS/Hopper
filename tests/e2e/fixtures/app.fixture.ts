import { test as base } from '@playwright/test';
import { currentUser, loginAs, logout } from '../helpers/auth';

type AppFixtures = {
  loginAsAdmin: () => Promise<void>;
  loginAsStudent: () => Promise<void>;
  logoutCurrentUser: () => Promise<void>;
  fetchCurrentUser: () => ReturnType<typeof currentUser>;
};

export const test = base.extend<AppFixtures>({
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

export { expect } from '@playwright/test';
