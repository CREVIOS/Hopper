import { expect, request as apiRequest } from '@playwright/test';
import { test } from '../fixtures/app.fixture';
import { e2eEnv } from '../helpers/env';
import { setupMockState } from '../helpers/mock';

async function signInThroughForm(
  page: Parameters<typeof test>[0]['page'],
  email: string,
  password: string
) {
  const response = await page.context().request.post('/api/auth/login', {
    data: { email, password }
  });
  expect(response.ok()).toBeTruthy();
  await page.goto('/dashboard');
  await expect(page).toHaveURL(/\/dashboard(?:\?.*)?$/);
}

test.describe('Suite 1: Authentication and authorization', () => {
  test('anonymous users land on the public homepage first', async ({ page }) => {
    await page.goto('/');

    await expect(page).toHaveURL(/\/$/);
    await expect(
      page.getByRole('heading', { level: 1, name: /Cloud VMs for\s*students\s*&\s*teams\./i })
    ).toBeVisible();
    await expect(page.getByRole('link', { name: 'Sign in' }).first()).toBeVisible();
  });

  test('TC-AUTH-001: student login reaches the dashboard and sets HttpOnly session cookies', async ({
    page
  }) => {
    await page.goto('/login');
    await expect(page.getByRole('heading', { name: 'Sign in with email' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'University SSO' })).toBeVisible();

    await signInThroughForm(page, e2eEnv.studentEmail, e2eEnv.studentPassword);
    await expect(page.getByText('Credit balance')).toBeVisible();

    const cookies = await page.context().cookies();
    const sessionCookie = cookies.find((cookie) => cookie.name === 'session_token');
    const refreshCookie = cookies.find((cookie) => cookie.name === 'refresh_token');
    expect(sessionCookie?.httpOnly).toBe(true);
    expect(refreshCookie?.httpOnly).toBe(true);
  });

  test('TC-AUTH-002: dashboard and navigation are role-scoped for student, professor, and admin', async ({
    page,
    logoutCurrentUser
  }) => {
    await page.goto('/login');
    await signInThroughForm(page, e2eEnv.studentEmail, e2eEnv.studentPassword);
    await expect(page.getByRole('link', { name: 'Virtual Machines' })).toBeVisible();
    await expect(
      page.getByRole('complementary').getByRole('link', { name: 'Credits', exact: true })
    ).toBeVisible();
    await expect(page.getByRole('link', { name: 'Admin' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Teaching' })).toHaveCount(0);

    await page.goto('/login');
    await signInThroughForm(page, e2eEnv.professorEmail, e2eEnv.professorPassword);
    await expect(page.getByRole('link', { name: 'Teaching' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Admin' })).toHaveCount(0);
    await logoutCurrentUser();

    await page.goto('/login');
    await signInThroughForm(page, e2eEnv.adminEmail, e2eEnv.adminPassword);
    await expect(page.getByRole('link', { name: 'Admin' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Teaching' })).toHaveCount(0);
  });

  test('TC-AUTH-003 and TC-AUTH-005: cross-tenant pod access is denied and unauthenticated API calls return 401', async ({
    page,
    request
  }) => {
    await setupMockState(request, {
      pods: [{ id: 'e2e-pod-99', user_id: 'student-3', plan: 'medium', template: 'python-ml' }]
    });

    await page.goto('/login');
    await signInThroughForm(page, e2eEnv.studentEmail, e2eEnv.studentPassword);

    const tenantResponse = await page.context().request.get(`${e2eEnv.controlURL}/pods/e2e-pod-99`);
    expect(tenantResponse.status()).toBe(403);

    await page.goto('/pods/e2e-pod-99');
    await expect(page.getByText('VM not found.')).toBeVisible();
    await expect(page.getByText(/vm-python-ml/i)).toHaveCount(0);

    const anonymous = await apiRequest.newContext({ baseURL: e2eEnv.baseURL });
    const anonymousResponse = await anonymous.get('/api/pods/');
    expect(anonymousResponse.status()).toBe(401);
    await anonymous.dispose();
  });

  test('TC-AUTH-004: expired access tokens refresh silently, then fall back to login once the refresh token is invalid', async ({
    page,
    request,
    loginAsStudent
  }) => {
    await loginAsStudent();

    await setupMockState(request, { session: { expired: true, refresh_valid: true } });
    await page.goto('/credits');
    await expect(page.getByRole('heading', { name: 'Credits' })).toBeVisible();

    await setupMockState(request, { session: { expired: true, refresh_valid: false } });
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/login$/);
  });
});
