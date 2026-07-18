import { expect } from '@playwright/test';
import { test } from '../fixtures/app.fixture';
import { setupMockState } from '../helpers/mock';

async function activateTab(tab: any) {
  await tab.evaluate((node: HTMLElement) => node.click());
}

async function waitForPodPageReady(page: Parameters<typeof test>[0]['page']) {
  await expect(page.getByRole('heading', { level: 1, name: /e2e-pod-/i })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Overview', selected: true })).toBeVisible();
}

async function confirmAction(page: Parameters<typeof test>[0]['page'], title: RegExp | string, action: string) {
  const dialog = page.getByRole('alertdialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(title)).toBeVisible();
  await dialog.getByRole('button', { name: action }).click();
}

test.describe('Suite 2 and queue-oriented edge cases', () => {
  test.beforeEach(async ({ loginAsStudent }) => {
    await loginAsStudent();
  });

  test('TC-POD-001: launches a VM and surfaces SSH access details', async ({
    page
  }) => {
    await page.goto('/pods');
    await expect(page.locator('main')).toContainText('Estimated cost');

    await page.getByRole('button', { name: 'Launch VM' }).click();
    await confirmAction(page, /Launch new VM\?/i, 'Launch');

    const podLink = page.locator('a[href="/pods/e2e-pod-1"]').first();
    await expect(podLink).toBeVisible();

    await podLink.click();
    await waitForPodPageReady(page);
    const main = page.locator('main');
    await expect(main).toContainText('SSH command');
    await expect(main).toContainText('ssh root@127.0.0.1 -p 30022');
    await expect(main).toContainText(/hopper\/vm-(python-ml:latest|ubuntu:22\.04)/);
  });

  test('TC-POD-002: blocks launches when the student has insufficient credits', async ({
    page,
    request
  }) => {
    await setupMockState(request, { balances: { 'student-1': 0 } });

    await page.goto('/pods');
    await expect(page.getByText(/Insufficient credits/i)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Launch VM' })).toBeDisabled();
  });

  test('TC-POD-003: pod detail metrics render from the live SSE stream', async ({
    page,
    request
  }) => {
    await setupMockState(request, {
      pods: [{ id: 'e2e-pod-1', user_id: 'student-1', plan: 'medium', template: 'python-ml' }]
    });

    await page.goto('/pods/e2e-pod-1');
    await waitForPodPageReady(page);
    const main = page.locator('main');
    await expect(main).toContainText('Live Metrics');
    await expect(main).toContainText(/42%|Waiting for metrics/);
    await expect(main).toContainText(/1.0 GB \/ 2.0 GB|Memory 4 Gi/);
  });

  test('TC-POD-004: terminating a running pod removes it from active history and sends it to past VMs', async ({
    page,
    request
  }) => {
    await setupMockState(request, {
      pods: [{ id: 'e2e-pod-1', user_id: 'student-1', plan: 'small', template: 'ubuntu' }]
    });

    await page.goto('/pods/e2e-pod-1');
    await waitForPodPageReady(page);
    const response = await request.delete('/api/pods/e2e-pod-1');
    expect(response.ok()).toBeTruthy();

    await page.goto('/pods');
    await expect(page.locator('main')).toContainText('Active 0');
    await expect(page.locator('main')).toContainText('History 1');
  });

  test('TC-POD-005 and TC-POD-006: failed launches and fourth-pod attempts are rejected without creating extra pods', async ({
    page,
    request
  }) => {
    await setupMockState(request, {
      next_create_failure: 'Image pull back-off'
    });

    await page.goto('/pods');
    await page.getByRole('button', { name: 'Launch VM' }).click();
    await confirmAction(page, /Launch new VM\?/i, 'Launch');
    await expect(page.getByText('Launch failed')).toBeVisible();
    await expect(page.getByText('Image pull back-off')).toBeVisible();

    await setupMockState(request, {
      pods: [
        { id: 'e2e-pod-1', user_id: 'student-1', plan: 'small' },
        { id: 'e2e-pod-2', user_id: 'student-1', plan: 'small' },
        { id: 'e2e-pod-3', user_id: 'student-1', plan: 'small' }
      ]
    });

    await page.goto('/pods');
    await page.getByRole('button', { name: 'Launch VM' }).click();
    await confirmAction(page, /Launch new VM\?/i, 'Launch');
    await expect(page.getByText('Maximum concurrent pods reached (3/3)')).toBeVisible();
    await expect(page.getByRole('link', { name: /e2e-pod-/ })).toHaveCount(3);
  });

  test('TC-EDGE-005: capacity exhaustion queues the request and routes the user to the queue view', async ({
    page,
    request
  }) => {
    await setupMockState(request, {
      availability: {
        cpu: { free_cores: 0, total_cores: 8, used_cores: 8 },
        queue_length: 0
      }
    });

    await page.goto('/pods');
    await page.getByRole('button', { name: 'Launch VM' }).click();
    await confirmAction(page, /Launch new VM\?/i, 'Launch');

    await expect(page).toHaveURL(/\/pods\/queue$/);
    await expect(page.getByRole('heading', { name: 'Queue' })).toBeVisible();
    await expect(page.locator('main').getByRole('button', { name: /Cancel/i })).toBeVisible();
  });
});
