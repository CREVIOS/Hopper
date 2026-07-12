import { expect, test } from '../fixtures/app.fixture';
import { authRequirementMessage, hasAuth } from '../helpers/env';

test.describe('Authorization', () => {
  test('keeps a student out of the admin console', async ({ page, loginAsStudent }) => {
    test.skip(!hasAuth('student'), authRequirementMessage('student'));

    await loginAsStudent();
    await page.goto('/admin');

    await expect(page).toHaveURL(/\/dashboard(?:\?.*)?$/);
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  });

  test('allows an admin to open the admin console and key management tabs', async ({
    page,
    loginAsAdmin
  }) => {
    test.skip(!hasAuth('admin'), authRequirementMessage('admin'));

    await loginAsAdmin();
    await page.goto('/admin');

    await expect(page.getByRole('heading', { name: 'Admin' })).toBeVisible();
    await expect(
      page.getByRole('main').getByText('Admin console', { exact: true })
    ).toBeVisible();
    await expect(page.getByRole('tab', { name: /users/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /active vms/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /audit log/i })).toBeVisible();
  });
});
