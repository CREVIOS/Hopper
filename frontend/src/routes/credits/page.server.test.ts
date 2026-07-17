import { describe, expect, it, vi } from 'vitest';

vi.mock('$lib/api/server', () => ({
  apiUrl: (path: string) => `http://api.test${path}`
}));

function cookieJar(token?: string) {
  return {
    get(name: string) {
      return name === 'session_token' ? token : undefined;
    }
  };
}

describe('credits page server load', () => {
  it('redirects anonymous users to login', async () => {
    const { load } = await import('./+page.server');

    await expect(
      load({
        parent: async () => ({ isAuthenticated: false })
      } as any)
    ).rejects.toMatchObject({
      status: 302,
      location: '/login'
    });
  });

  it('returns balance and transactions for authenticated users', async () => {
    const { load } = await import('./+page.server');
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith('/credits/balance')) {
        return { ok: true, json: async () => ({ balance: 42 }) };
      }
      return { ok: true, json: async () => [{ id: 'txn-1', amount: -3 }] };
    });

    const result = await load({
      parent: async () => ({ isAuthenticated: true }),
      fetch: fetchMock,
      cookies: cookieJar('session-token')
    } as any);

    expect(result).toEqual({
      balance: 42,
      transactions: [{ id: 'txn-1', amount: -3 }]
    });
  });
});
