import { expect, test } from '@playwright/test';

const protectedRoutes = [
  '/dashboard',
  '/pods',
  '/pods/test-pod',
  '/credits',
  '/settings',
  '/settings/ssh-keys',
  '/admin',
  '/teacher'
];

for (const route of protectedRoutes) {
  test(`redirects unauthenticated access to ${route}`, async ({ page }) => {
    await page.goto(route);
    await expect(page).toHaveURL(/\/login(?:\?.*)?$/);
  });
}

const publicPages = [
  { route: '/login', heading: 'Welcome back' },
  { route: '/signup', heading: /Create your/i },
  { route: '/forgot-password', heading: 'Reset your password' },
  { route: '/verify-email', heading: 'Verify your email' }
];

for (const publicPage of publicPages) {
  test(`renders public page ${publicPage.route}`, async ({ page }) => {
    await page.goto(publicPage.route);
    await expect(page.getByRole('heading', { name: publicPage.heading })).toBeVisible();
  });
}

test('login email field uses an email input', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByLabel('Email')).toHaveAttribute('type', 'email');
});

test('login password field masks its value', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByLabel('Password')).toHaveAttribute('type', 'password');
});

test('login links to password recovery', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByRole('link', { name: /forgot password/i })).toHaveAttribute(
    'href',
    '/forgot-password'
  );
});

test('login links to account creation', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByRole('link', { name: /create an account/i })).toHaveAttribute(
    'href',
    '/signup'
  );
});

test('signup offers student registration', async ({ page }) => {
  await page.goto('/signup');
  await expect(page.getByText('Student', { exact: true })).toBeVisible();
});

test('signup offers teacher registration', async ({ page }) => {
  await page.goto('/signup');
  await expect(page.getByText('Teacher', { exact: true })).toBeVisible();
});

test('signup exposes its account creation action', async ({ page }) => {
  await page.goto('/signup');
  await expect(page.getByRole('button', { name: /create account/i })).toBeVisible();
});
