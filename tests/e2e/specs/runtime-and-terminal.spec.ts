import { expect } from '@playwright/test';
import { test } from '../fixtures/app.fixture';
import { setupMockState } from '../helpers/mock';

async function activateTab(tab: any) {
  await tab.evaluate((node: HTMLElement) => node.click());
}

async function waitForPodPageReady(page: Parameters<typeof test>[0]['page']) {
  await expect(page.getByRole('textbox', { name: 'Terminal input' })).toBeVisible();
}

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
    await waitForPodPageReady(page);

    const rows = page.locator('.xterm-rows');
    await expect(rows).toContainText('Connected!');

    await page.locator('.xterm-helper-textarea').pressSequentially('pwd');
    await page.locator('.xterm-helper-textarea').press('Enter');
    await expect(rows).toContainText('/workspace');
  });

  test('the terminal workspace keeps runtime controls available while VM metrics continue rendering', async ({
    page,
    loginAsStudent
  }) => {
    await loginAsStudent();
    await page.goto('/pods/e2e-pod-1');
    await waitForPodPageReady(page);

    await expect(page.getByRole('button', { name: 'New terminal' })).toBeVisible();
    const main = page.locator('main');
    await expect(main).toContainText('Live metrics');
    await expect(main).toContainText(/Waiting for metrics|Streaming/);
  });
});
