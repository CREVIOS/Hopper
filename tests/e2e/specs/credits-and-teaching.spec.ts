import { expect } from '@playwright/test';
import { test } from '../fixtures/app.fixture';
import { setupMockState } from '../helpers/mock';

test.describe('Suite 3: credits and teaching workflows', () => {
  test('TC-CREDIT-001 baseline: the credits page renders current balance and ledger history', async ({
    page,
    request,
    loginAsStudent
  }) => {
    await setupMockState(request, {
      balances: { 'student-1': 87.5 },
      transactions: [
        {
          account_id: 'student-1',
          user_id: 'student-1',
          amount: 2,
          direction: 'debit',
          type: 'pod_launch_hold',
          pod_id: 'e2e-pod-1'
        }
      ]
    });

    await loginAsStudent();
    await page.goto('/credits');

    await expect(page.getByRole('heading', { name: 'Credits' })).toBeVisible();
    await expect(page.getByText('87.50')).toBeVisible();
    await expect(page.getByText(/pod launch hold/i)).toBeVisible();
  });

  test('TC-CREDIT-004: a professor can allocate credits to a student from the teaching console', async ({
    page,
    loginAsProfessor
  }) => {
    await loginAsProfessor();
    await page.goto('/teacher');

    await expect(page.getByRole('heading', { name: 'Teaching' })).toBeVisible();
    await page.getByRole('button', { name: 'Allocate' }).first().click();

    const dialog = page.getByRole('dialog', { name: 'Allocate credits' });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel('Amount').fill('50');
    await dialog.getByRole('button', { name: 'Allocate' }).click();

    await expect(page.getByText('450.00')).toBeVisible();
    await expect(page.getByRole('cell', { name: '150.00' }).first()).toBeVisible();
  });

  test('TC-CREDIT-002: the dashboard warns when the student balance is low', async ({
    page,
    request,
    loginAsStudent
  }) => {
    await setupMockState(request, {
      balances: { 'student-1': 9.5 },
      pods: [{ id: 'e2e-pod-1', user_id: 'student-1', plan: 'medium', template: 'python-ml' }]
    });

    await loginAsStudent();
    await page.goto('/dashboard');

    await expect(page.getByText('Low balance: 9.50 credits remaining')).toBeVisible();
    await expect(page.getByText(/About 4h 45m left at the current burn rate/i)).toBeVisible();
  });

  test('teacher console disables allocations when the professor has no budget left', async ({
    page,
    request,
    loginAsProfessor
  }) => {
    await setupMockState(request, { balances: { 'professor-1': 0 } });

    await loginAsProfessor();
    await page.goto('/teacher');

    await expect(
      page.getByText(/An admin needs to grant you a budget before you can allocate to students/i)
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Allocate' }).first()).toBeDisabled();
  });
});
