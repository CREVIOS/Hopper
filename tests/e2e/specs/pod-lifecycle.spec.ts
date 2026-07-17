import { expect } from '@playwright/test';
import { test } from '../fixtures/app.fixture';
import { setupMockState } from '../helpers/mock';

async function confirmDialog(page: Parameters<typeof test>[0]['page'], title: RegExp | string, action: string) {
  await expect(page.getByText(title).last()).toBeVisible();
  await page.getByRole('button', { name: action }).last().click();
}

test.describe('Suite 2 and queue-oriented edge cases', () => {
  test.beforeEach(async ({ loginAsStudent }) => {
    await loginAsStudent();
  });

  test('TC-POD-001: launches a medium Python VM and surfaces SSH access details', async ({
    page
  }) => {
    await page.goto('/pods');
    await page.getByRole('button', { name: /^medium\b/i }).click();
    await page.getByRole('button', { name: /^python \/ ml\b/i }).click();

    await expect(page.getByText(/2 credits?.*hour/i)).toBeVisible();

    await page.getByRole('button', { name: 'Launch VM' }).click();
    await confirmDialog(page, /Launch new VM\?/, 'Launch');

    const podLink = page.locator('a[href="/pods/e2e-pod-1"]').first();
    await expect(podLink).toBeVisible();

    await podLink.click();
    await expect(page.getByText('SSH command')).toBeVisible();
    await expect(page.getByText('ssh root@127.0.0.1 -p 30022')).toBeVisible();
    await expect(page.getByText('hopper/vm-python-ml:latest')).toBeVisible();
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
    await page.getByRole('tab', { name: 'Metrics' }).click();

    await expect(page.getByText('Live metrics')).toBeVisible();
    await expect(page.getByText('42%')).toBeVisible();
    await expect(page.getByText('1.0 GiB / 2.0 GiB')).toBeVisible();
  });

  test('TC-POD-004: terminating a running pod removes it from active history and sends it to past VMs', async ({
    page,
    request
  }) => {
    await setupMockState(request, {
      pods: [{ id: 'e2e-pod-1', user_id: 'student-1', plan: 'small', template: 'ubuntu' }]
    });

    await page.goto('/pods/e2e-pod-1');
    await page.getByRole('button', { name: 'Terminate' }).click();
    await confirmDialog(page, /Terminate VM/i, 'Terminate');

    await expect(page).toHaveURL(/\/pods(?:\?.*)?$/);
    await page.getByRole('tab', { name: /History/i }).click();
    await expect(page.getByRole('link', { name: /e2e-pod-1/i })).toBeVisible();
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
    await confirmDialog(page, /Launch new VM\?/, 'Launch');
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
    await confirmDialog(page, /Launch new VM\?/, 'Launch');
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
    await confirmDialog(page, /Launch new VM\?/, 'Launch');

    await expect(page).toHaveURL(/\/pods\/queue$/);
    await expect(page.getByRole('heading', { name: 'Queue' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Position' })).toBeVisible();
  });
});
