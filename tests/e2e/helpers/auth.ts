import { expect, type APIRequestContext, type Page } from '@playwright/test';
import {
  authRequirementMessage,
  e2eEnv,
  resolveAuthMode,
  type AuthRole
} from './env';

type AuthenticatedUser = {
  id: string;
  email: string;
  name: string;
  role: string;
  pending_teacher?: boolean;
};

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export async function loginAs(page: Page, role: AuthRole): Promise<void> {
  const mode = resolveAuthMode(role);
  if (mode === 'missing') {
    throw new Error(authRequirementMessage(role));
  }

  if (mode === 'password') {
    const email = role === 'admin' ? e2eEnv.adminEmail : e2eEnv.studentEmail;
    const password = role === 'admin' ? e2eEnv.adminPassword : e2eEnv.studentPassword;

    await page.goto('/login');
    await page.getByLabel('Email').fill(email!);
    await page.getByLabel('Password').fill(password!);
    await page.getByRole('button', { name: /^sign in$/i }).click();
  } else {
    const path = role === 'admin' ? '/dev-login?as=admin' : '/dev-login?as=user';
    await page.goto(path);
  }

  await expect(page).toHaveURL(/\/dashboard(?:\?.*)?$/);
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
}

export async function currentUser(request: APIRequestContext): Promise<AuthenticatedUser> {
  const response = await request.get('/api/auth/me');
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as AuthenticatedUser;
}

export async function logout(page: Page): Promise<void> {
  const user = await currentUser(page.context().request);
  const triggerName = new RegExp(`^User menu for ${escapeRegExp(user.name || user.email)}$`, 'i');

  const trigger = page.getByRole('button', { name: triggerName });
  const signOut = page.getByRole('menuitem', { name: /sign out/i });
  await expect(trigger).toBeVisible();
  await expect(trigger).toHaveAttribute('data-hydrated', 'true');
  await trigger.click();
  await expect(signOut).toBeVisible();
  await signOut.click();
  await expect(page).toHaveURL(/\/login(?:\?.*)?$/);

  const cookies = await page.context().cookies();
  expect(cookies.map((cookie) => cookie.name)).not.toEqual(
    expect.arrayContaining(['session_token', 'refresh_token', 'id_token'])
  );
  await expect
    .poll(() => page.evaluate(() => [localStorage.length, sessionStorage.length]))
    .toEqual([0, 0]);
}
