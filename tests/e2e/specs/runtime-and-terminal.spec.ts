import { expect } from '@playwright/test';
import { test } from '../fixtures/app.fixture';
import { setupMockState } from '../helpers/mock';

test.describe('Suite 4 and runtime interactions', () => {
  test.beforeEach(async ({ request }) => {
    await setupMockState(request, {
      pods: [{ id: 'e2e-pod-1', user_id: 'student-1', plan: 'medium', template: 'python-ml' }]
    });
  });

  test('TC-TERM-001: the terminal tab opens a live websocket-backed shell', async ({
    page,
    loginAsStudent
  }) => {
    await loginAsStudent();
    await page.goto('/pods/e2e-pod-1');

    const rows = page.locator('.xterm-rows');
    await expect(rows).toContainText('Connected!');

    await page.locator('.xterm-helper-textarea').pressSequentially('pwd');
    await page.locator('.xterm-helper-textarea').press('Enter');
    await expect(rows).toContainText('/workspace');
  });

  test('terminal tabs can be added and the metrics tab still renders while the VM is running', async ({
    page,
    loginAsStudent
  }) => {
    await loginAsStudent();
    await page.goto('/pods/e2e-pod-1');

    await page.getByRole('button', { name: 'New terminal' }).click();
    await expect(page.getByRole('button', { name: 'Close terminal' })).toHaveCount(2);

    await page.getByRole('tab', { name: 'Metrics' }).click();
    await expect(page.getByText('Streaming')).toBeVisible();
    await expect(page.getByText('Healthy')).toBeVisible();
  });
});
