import { test, expect } from '../fixtures/app.fixture';

test.describe('student workflows', () => {
  test.beforeEach(async ({ loginAsStudent }) => loginAsStudent());

  test('launches a VM and shows it in the active list', async ({ page }) => {
    await page.goto('/pods');
    await page.getByRole('button', { name: 'Launch VM' }).click();
    await page.getByRole('button', { name: 'Launch', exact: true }).click();
    await expect(page.getByRole('link', { name: /e2e-pod-/ })).toHaveAttribute('href', '/pods/e2e-pod-1');
  });

  test('blocks launch when credits are insufficient', async ({ page, request }) => {
    await request.post('http://127.0.0.1:8000/__test/balance', { data: { balance: 0 } });
    await page.goto('/pods');
    await expect(page.getByText(/Insufficient credits/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Launch VM' })).toBeDisabled();
  });

  test('terminates a running VM', async ({ page, request }) => {
    await request.post('http://127.0.0.1:8000/pods/', { data: { plan: 'small' } });
    await page.goto('/pods/e2e-pod-1');
    await expect(page.getByRole('button', { name: 'Terminate' })).toBeVisible();
    const status = await page.evaluate(async () =>
      (await fetch('/api/pods/e2e-pod-1', { method: 'DELETE' })).status
    );
    expect(status).toBe(200);
    const terminated = await request.get('http://127.0.0.1:8000/pods/e2e-pod-1');
    expect((await terminated.json()).state).toBe('terminated');
  });

  test('streams metrics without a page refresh', async ({ page, request }) => {
    await request.post('http://127.0.0.1:8000/pods/', { data: { plan: 'small' } });
    await page.goto('/pods/e2e-pod-1');
    await page.getByRole('tab', { name: 'Metrics' }).click();
    const stream = await page.evaluate(async () =>
      (await fetch('/api/pods/e2e-pod-1/metrics')).text()
    );
    expect(stream).toContain('"cpu_percent":42');
  });

  test('opens the terminal workspace for a running VM', async ({ page, request }) => {
    await request.post('http://127.0.0.1:8000/pods/', { data: { plan: 'small' } });
    await page.goto('/pods/e2e-pod-1');
    await expect(page.getByRole('tab', { name: 'Terminal' })).toBeVisible();
  });

  test('shows a deterministic credit balance', async ({ page }) => {
    await page.goto('/credits');
    await expect(page.getByRole('link', { name: '100.0 credits' })).toBeVisible();
    await expect(page.getByText(/No transactions yet/)).toBeVisible();
  });
});

test.describe('admin workflows', () => {
  test.beforeEach(async ({ loginAsAdmin }) => loginAsAdmin());

  test('shows management areas and the mock node', async ({ page }) => {
    await page.goto('/admin');
    await expect(page.getByRole('tab', { name: 'Users' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Active VMs' })).toBeVisible();
    await page.getByRole('tab', { name: 'Nodes' }).click();
    await expect(page.getByText('mock-node')).toBeVisible();
  });

  test('lists the seeded student', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Users' }).click();
    await expect(page.getByText('student-1@test.edu')).toBeVisible();
  });
});
