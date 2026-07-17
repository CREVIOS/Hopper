import { expect, request as apiRequest } from '@playwright/test';
import { test } from '../fixtures/app.fixture';

test.describe('Real-stack authentication', () => {
  test('anonymous API access still returns 401 on the live stack', async () => {
    const anonymous = await apiRequest.newContext({ baseURL: process.env.BASE_URL });
    const response = await anonymous.get('/api/pods/');
    expect(response.status()).toBe(401);
    await anonymous.dispose();
  });
});
