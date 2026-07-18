import { afterEach, describe, expect, it, vi } from 'vitest';

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

afterEach(() => {
  vi.clearAllMocks();
});

describe('queue page server load', () => {
  it('redirects anonymous users to login', async () => {
    const { load } = await import('./queue/+page.server');

    await expect(
      load({
        parent: async () => ({ isAuthenticated: false })
      } as any)
    ).rejects.toMatchObject({
      status: 302,
      location: '/login'
    });
  });

  it('returns queue entries for authenticated users and forwards cookies', async () => {
    const { load } = await import('./queue/+page.server');
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      expect(init?.headers).toEqual({ Cookie: 'session_token=queue-token' });
      return {
        ok: true,
        json: async () => [{ id: 'entry-1', state: 'queued' }]
      };
    });

    const result = await load({
      parent: async () => ({ isAuthenticated: true }),
      fetch: fetchMock,
      cookies: cookieJar('queue-token')
    } as any);

    expect(result).toEqual({
      entries: [{ id: 'entry-1', state: 'queued' }]
    });
  });

  it('returns an empty queue when the API is unavailable', async () => {
    const { load } = await import('./queue/+page.server');

    const result = await load({
      parent: async () => ({ isAuthenticated: true }),
      fetch: vi.fn().mockRejectedValue(new Error('offline')),
      cookies: cookieJar()
    } as any);

    expect(result).toEqual({ entries: [] });
  });

  it('returns an empty queue when the API responds with an error', async () => {
    const { load } = await import('./queue/+page.server');

    const result = await load({
      parent: async () => ({ isAuthenticated: true }),
      fetch: vi.fn().mockResolvedValue({ ok: false }),
      cookies: cookieJar()
    } as any);

    expect(result).toEqual({ entries: [] });
  });
});
