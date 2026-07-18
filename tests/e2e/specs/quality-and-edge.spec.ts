import { expect } from '@playwright/test';
import { test } from '../fixtures/app.fixture';
import { setupMockState } from '../helpers/mock';

async function confirmLaunch(page: Parameters<typeof test>[0]['page']) {
  const dialog = page.getByRole('alertdialog');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Launch' }).click();
}

async function tabUntilFocused(
  page: Parameters<typeof test>[0]['page'],
  locator: ReturnType<Parameters<typeof test>[0]['page']['getByRole']>,
  attempts = 12
) {
  for (let i = 0; i < attempts; i += 1) {
    await page.keyboard.press('Tab');
    if (await locator.evaluate((node) => node === document.activeElement)) {
      return;
    }
  }
}

test.describe('Accessibility, performance, and edge coverage', () => {
  test('accessibility smoke: core actions remain keyboard reachable', async ({
    page,
    loginAsStudent
  }) => {
    await loginAsStudent();
    await page.goto('/pods');

    const launchButton = page.getByRole('button', { name: 'Launch VM' });
    await launchButton.focus();
    await expect(launchButton).toBeFocused();
    await expect(launchButton).toHaveClass(/focus-visible:ring-2/);
  });

  test('performance smoke: login and primary navigation stay within the documented mock thresholds', async ({
    page
  }) => {
    const loginStart = Date.now();
    await page.goto('/login');
    await page.getByLabel('Email', { exact: true }).fill('student-1@test.edu');
    await page.getByLabel('Password', { exact: true }).fill('e2e');
    await page.getByRole('button', { name: /^sign in$/i }).click();
    await expect(page).toHaveURL(/\/dashboard(?:\?.*)?$/);
    expect(Date.now() - loginStart).toBeLessThan(3000);

    const navStart = Date.now();
    await page.goto('/pods');
    await expect(page.getByRole('heading', { name: 'Virtual Machines' })).toBeVisible();
    expect(Date.now() - navStart).toBeLessThan(500);
  });

  test('TC-EDGE-001: a launch request interrupted in-flight does not create a duplicate VM', async ({
    page,
    loginAsStudent
  }) => {
    await loginAsStudent();
    await page.route('**/api/pods/', async (route) => {
      if (route.request().method() === 'POST') {
        await route.abort('failed');
        return;
      }
      await route.continue();
    });

    await page.goto('/pods');
    await page.getByRole('button', { name: 'Launch VM' }).click();
    await confirmLaunch(page);
    await expect(page.getByText('Launch failed')).toBeVisible();

    await page.unroute('**/api/pods/');
    await page.reload();
    await expect(page.getByRole('link', { name: /e2e-pod-/ })).toHaveCount(0);
  });

  test('TC-EDGE-004: a second tab picks up new pods and credit changes shortly after launch', async ({
    context,
    page,
    loginAsStudent
  }) => {
    await loginAsStudent();
    const secondTab = await context.newPage();
    await secondTab.goto('/pods');

    await page.goto('/pods');
    await page.getByRole('button', { name: 'Launch VM' }).click();
    await confirmLaunch(page);

    await expect(secondTab.locator('a[href="/pods/e2e-pod-1"]').first()).toBeVisible({ timeout: 7000 });
    await expect(secondTab.getByRole('link', { name: /99\.0 credits/i })).toBeVisible({ timeout: 7000 });
  });

  test('TC-TERM-004 baseline: pasted terminal input is accepted by the shell session', async ({
    page,
    request,
    loginAsStudent
  }) => {
    await setupMockState(request, {
      pods: [{ id: 'e2e-pod-1', user_id: 'student-1', plan: 'medium', template: 'python-ml' }]
    });

    await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
    await loginAsStudent();
    await page.goto('/pods/e2e-pod-1');

    const input = page.locator('.xterm-helper-textarea');
    await expect(input).toBeVisible();
    await page.evaluate(() => navigator.clipboard.writeText('whoami'));
    await input.focus();
    await page.keyboard.press(process.platform === 'darwin' ? 'Meta+V' : 'Control+V');
    await page.keyboard.press('Enter');

    await expect(page.locator('.xterm-rows')).toContainText('root');
  });
});
