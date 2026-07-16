import { expect, test } from '../fixtures/app.fixture';
import { authRequirementMessage, hasAuth } from '../helpers/env';

test.describe('Student Dashboard', () => {
  test.skip(!hasAuth('student'), authRequirementMessage('student'));

  test.beforeEach(async ({ loginAsStudent }) => {
    await loginAsStudent();
  });

  test('shows the student dashboard after authentication', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    await expect(
      page.getByText(/manage your virtual machines, monitor usage, and track credit spend/i)
    ).toBeVisible();
  });

  test('renders the core dashboard stat cards including credit balance', async ({ page }) => {
    await expect(page.getByText('Credit balance')).toBeVisible();
    await expect(page.getByRole('link', { name: /^Active VMs\b/ })).toBeVisible();
    await expect(page.getByText('Avg CPU (24h)')).toBeVisible();
    await expect(page.getByText('Avg memory (24h)')).toBeVisible();
  });

  test('shows the active-vm section with either pods or the empty state', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Active VMs' })).toBeVisible();

    const emptyState = page.getByText(/no active vms right now/i);
    const vmCards = page.getByText(/^Created /).first();

    await expect(emptyState.or(vmCards)).toBeVisible();
  });
});
