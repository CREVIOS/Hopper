import { expect } from '@playwright/test';
import { test } from '../fixtures/app.fixture';
import { setupMockState } from '../helpers/mock';

test.describe('Suite 5: admin workflows', () => {
  test.beforeEach(async ({ loginAsAdmin }) => {
    await loginAsAdmin();
  });

  test('TC-ADMIN-001 and TC-ADMIN-004: the admin console shows overview stats, active VMs, and node inventory', async ({
    page,
    request
  }) => {
    await setupMockState(request, {
      pods: [{ id: 'e2e-pod-1', user_id: 'student-1', plan: 'medium', template: 'python-ml' }]
    });

    await page.goto('/admin');
    await expect(page.getByRole('heading', { name: 'Admin' })).toBeVisible();
    await expect(page.getByText('Total users')).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Active VMs' })).toBeVisible();

    await page.getByRole('tab', { name: 'Nodes' }).click();
    await expect(page.getByRole('tabpanel', { name: 'Nodes' }).getByText('mock-node')).toBeVisible();

    await page.getByRole('tab', { name: 'Active VMs' }).click();
    await expect(
      page.getByRole('tabpanel', { name: 'Active VMs' }).getByText(/student-1@test\.edu/i)
    ).toBeVisible();
  });

  test('TC-ADMIN-002: the admin can search for a user, allocate credits, and change their role', async ({
    page
  }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Users' }).click();
    const usersPanel = page.getByRole('tabpanel', { name: 'Users' });
    await usersPanel.getByPlaceholder('Search users…').fill('student-1@test.edu');
    await expect(usersPanel.getByText('student-1@test.edu').first()).toBeVisible();

    await usersPanel.getByRole('button', { name: 'Allocate' }).first().click();
    const allocateDialog = page.getByRole('dialog', { name: 'Allocate credits' });
    await allocateDialog.getByLabel('Amount').fill('25');
    await allocateDialog.getByRole('button', { name: 'Allocate' }).click();
    await expect(page.getByText('Allocated 25.00 credits')).toBeVisible();

    await page.getByLabel('Change role for student-1@test.edu').click();
    await page.getByRole('menuitem', { name: /professor/i }).click();
    await expect(page.getByText('professor')).toBeVisible();
  });

  test('teacher approval requests can be processed from the admin console', async ({
    page
  }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: /Requests/i }).click();
    const requestsPanel = page.getByRole('tabpanel', { name: /Requests/i });
    await expect(
      requestsPanel.getByRole('cell', { name: 'teacher-pending@test.edu', exact: true })
    ).toBeVisible();
    await requestsPanel.getByRole('button', { name: 'Approve' }).click();
    await expect(
      requestsPanel.getByRole('cell', { name: 'teacher-pending@test.edu', exact: true })
    ).toHaveCount(0);
  });
});
