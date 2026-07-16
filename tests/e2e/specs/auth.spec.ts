import { expect, test } from '../fixtures/app.fixture';
import { authRequirementMessage, hasAuth } from '../helpers/env';

test.describe('Authentication', () => {
  test('redirects an unauthenticated user away from the dashboard', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/login(?:\?.*)?$/);
  });

  test('renders the login form and supported actions', async ({ page }) => {
    await page.goto('/login');

    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
    await expect(page.getByLabel('Email')).toBeVisible();
    await expect(page.getByLabel('Password')).toBeVisible();
    await expect(page.getByRole('button', { name: /^sign in$/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /sign in as admin/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /create an account/i })).toBeVisible();
  });

  test('shows a useful error for invalid credentials', async ({ page }) => {
    await page.goto('/login');

    await page.getByLabel('Email').fill('invalid-user@example.com');
    await page.getByLabel('Password').fill('definitely-wrong-password');
    const loginResponse = page.waitForResponse(
      (response) => new URL(response.url()).pathname.endsWith('/auth/login') && response.status() === 401
    );
    await page.getByRole('button', { name: /^sign in$/i }).click();
    await loginResponse;

    await expect(
      page.getByText(/invalid email or password|login failed|sign-in failed/i)
    ).toBeVisible();
    await expect(page).toHaveURL(/\/login(?:\?.*)?$/);
  });

  test('allows a signed-in student to log out and lose protected access', async ({
    page,
    loginAsStudent,
    logoutCurrentUser
  }) => {
    test.skip(!hasAuth('student'), authRequirementMessage('student'));

    await loginAsStudent();
    await logoutCurrentUser();

    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/login(?:\?.*)?$/);
  });
});
