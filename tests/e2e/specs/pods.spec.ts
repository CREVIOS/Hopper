import { expect, test } from '../fixtures/app.fixture';
import { authRequirementMessage, hasAuth } from '../helpers/env';

test.describe('Student VM Management', () => {
  test.skip(!hasAuth('student'), authRequirementMessage('student'));

  test.beforeEach(async ({ page, loginAsStudent }) => {
    await loginAsStudent();
    await page.goto('/pods');
  });

  test('renders the VM launch workflow with plans, templates, and launch controls', async ({
    page
  }) => {
    await expect(page.getByRole('heading', { name: 'Virtual Machines' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Launch a new VM' })).toBeVisible();

    await expect(page.getByRole('button', { name: /^small\b/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /^medium\b/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /^large\b/i })).toBeVisible();

    await expect(page.getByRole('button', { name: /^ubuntu 22\.04\b/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /^python \/ ml\b/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /^c \/ c\+\+(?:\s|$)/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /^java/i })).toBeVisible();

    await expect(page.getByRole('button', { name: /launch vm/i })).toBeVisible();
  });

  test('shows VM list filters and a deterministic list or empty-state container', async ({
    page
  }) => {
    await expect(page.getByRole('heading', { name: 'Your VMs' })).toBeVisible();
    await expect(page.getByPlaceholder('Search ID, image, plan…')).toBeVisible();
    await expect(page.getByRole('tab', { name: /active/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /history/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /^all$/i })).toBeVisible();

    const emptyState = page.getByText(/no active vms|you haven't created any vms yet/i);
    const vmCard = page.getByText(/^Created /).first();

    await expect(emptyState.or(vmCard)).toBeVisible();
  });
});
