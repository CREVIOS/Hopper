import { expect, request as apiRequest } from '@playwright/test';
import { test } from '../fixtures/app.fixture';

test.describe('Real-stack authentication', () => {
  test('student password login reaches the dashboard against live Keycloak and API', async ({
    page,
    loginAsStudent
  }) => {
    await page.goto('/login');
    await loginAsStudent();
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByText('Credit balance')).toBeVisible();
  });

  test('role-specific navigation reflects live Keycloak roles', async ({
    page,
    loginAsAdmin,
    loginAsProfessor
  }) => {
    await loginAsProfessor();
    await expect(page.getByRole('link', { name: 'Teaching' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Admin' })).toHaveCount(0);

    await page.goto('/login');
    await loginAsAdmin();
    await expect(page.getByRole('link', { name: 'Admin' })).toBeVisible();
  });

  test('anonymous API access still returns 401 on the live stack', async () => {
    const anonymous = await apiRequest.newContext({ baseURL: process.env.BASE_URL });
    const response = await anonymous.get('/api/pods/');
    expect(response.status()).toBe(401);
    await anonymous.dispose();
  });
});
