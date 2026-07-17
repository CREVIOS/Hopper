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

describe('dashboard page server load', () => {
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

  it('returns balance, pods, recent history, and summary for authenticated users', async () => {
    const { load } = await import('./+page.server');
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith('/credits/balance')) {
        return { ok: true, json: async () => ({ balance: 5.5 }) };
      }
      if (url.endsWith('/pods/')) {
        return { ok: true, json: async () => [{ id: 'pod-1' }] };
      }
      if (url.endsWith('/credits/history?limit=5')) {
        return { ok: true, json: async () => [{ amount: -1 }] };
      }
      return {
        ok: true,
        json: async () => ({
          pod_count: 1,
          avg_cpu_percent: 22,
          avg_memory_bytes: 1024
        })
      };
    });

    const result = await load({
      parent: async () => ({ isAuthenticated: true }),
      fetch: fetchMock,
      cookies: cookieJar('session-token')
    } as any);

    expect(result).toEqual({
      balance: 5.5,
      pods: [{ id: 'pod-1' }],
      recent: [{ amount: -1 }],
      summary: {
        pod_count: 1,
        avg_cpu_percent: 22,
        avg_memory_bytes: 1024
      }
    });
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });
});
