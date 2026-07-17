import { expect, type APIRequestContext } from '@playwright/test';
import { e2eEnv } from './env';

type MockSetup = {
  session?: {
    expired?: boolean;
    refresh_valid?: boolean;
  };
  balances?: Record<string, number>;
  availability?: {
    cpu?: { total_cores?: number | null; used_cores?: number | null; free_cores?: number | null };
    memory?: { total_gib?: number | null; used_gib?: number | null; free_gib?: number | null };
    storage?: { total_gib?: number | null; used_gib?: number | null; free_gib?: number | null };
    nodes_ready?: number | null;
    queue_length?: number;
  };
  pods?: Array<Record<string, unknown>>;
  queue?: Array<Record<string, unknown>>;
  teacher_requests?: Array<Record<string, unknown>>;
  users?: Array<Record<string, unknown>>;
  next_create_failure?: string | null;
};

export async function setupMockState(
  request: APIRequestContext,
  payload: MockSetup
): Promise<void> {
  const response = await request.post(`${e2eEnv.controlURL}/__test/setup`, { data: payload });
  expect(response.ok()).toBeTruthy();
}
