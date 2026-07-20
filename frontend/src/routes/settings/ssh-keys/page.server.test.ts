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

describe('ssh keys page server load', () => {
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

  it('returns keys for authenticated users', async () => {
    const { load } = await import('./+page.server');
    const fetchMock = vi.fn(async (url: string) => ({
      ok: true,
      json: async () =>
        url.endsWith('/auth/api-keys')
          ? [{ id: 'ak-1', name: 'ci', prefix: 'hpk_ab', scope: 'read_only' }]
          : [{ id: 'key-1', name: 'laptop' }]
    }));

    const result = await load({
      parent: async () => ({ isAuthenticated: true }),
      fetch: fetchMock,
      cookies: cookieJar('session-token')
    } as any);

    // The loader fetches SSH keys and API keys in parallel; the mock returns a
    // distinct fixture per endpoint (/auth/api-keys vs the SSH-keys list).
    expect(result).toEqual({
      keys: [{ id: 'key-1', name: 'laptop' }],
      apiKeys: [{ id: 'ak-1', name: 'ci', prefix: 'hpk_ab', scope: 'read_only' }]
    });
  });
});
