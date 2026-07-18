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

  test('TC-TERM-002: the terminal viewport resizes with the browser window', async ({
    page,
    loginAsStudent
  }) => {
    await loginAsStudent();
    await page.goto('/pods/e2e-pod-1');
    await waitForPodPageReady(page);

    const terminal = page.locator('.xterm');
    const before = await terminal.boundingBox();
    expect(before).not.toBeNull();

    await page.setViewportSize({ width: 900, height: 700 });
    await page.waitForTimeout(250);

    const after = await terminal.boundingBox();
    expect(after).not.toBeNull();
    expect(after!.width).toBeLessThan(before!.width);
  });

  test('TC-TERM-003: the terminal shows reconnect state and recovers after a dropped websocket', async ({
    page,
    request,
    loginAsStudent
  }) => {
    await setupMockState(request, {
      terminal: { disconnect_on_connect: true, disconnect_after_ms: 500 },
      pods: [{ id: 'e2e-pod-1', user_id: 'student-1', plan: 'medium', template: 'python-ml' }]
    });

    await loginAsStudent();
    await page.goto('/pods/e2e-pod-1');
    await waitForPodPageReady(page);

    const rows = page.locator('.xterm-rows');
    await expect(rows).toContainText(/Reconnecting|Attempt 1\/5/i, { timeout: 10000 });
    await expect(rows).toContainText(/Connected!/i, { timeout: 10000 });
  });

  test('TC-EDGE-002: closing the browser tab does not end the running VM', async ({
    page,
    context,
    loginAsStudent
  }) => {
    await loginAsStudent();
    await page.goto('/dashboard');
    await expect(page.getByRole('heading', { name: 'Active VMs' })).toBeVisible();
    await page.close();

    const reopened = await context.newPage();
    await reopened.goto('/dashboard');
    await expect(reopened.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    await expect(reopened.locator('a[href="/pods/e2e-pod-1"]').first()).toBeVisible();
  });
});
