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

async function importPage(nodeIp?: string) {
  vi.resetModules();
  vi.doMock('$env/dynamic/private', () => ({
    env: nodeIp ? { NODE_IP: nodeIp } : {}
  }));
  return import('./+page.server');
}

afterEach(() => {
  vi.resetModules();
  vi.unmock('$env/dynamic/private');
});

describe('pods page server load', () => {
  it('redirects anonymous users to login', async () => {
    const { load } = await importPage();

    await expect(
      load({
        parent: async () => ({ isAuthenticated: false })
      } as any)
    ).rejects.toMatchObject({
      status: 302,
      location: '/login'
    });
  });

  it('returns pod data, balance, and availability', async () => {
    const { load } = await importPage('10.0.0.5');
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith('/pods/')) {
        return { ok: true, json: async () => [{ id: 'pod-1' }] };
      }
      if (url.endsWith('/credits/balance')) {
        return { ok: true, json: async () => ({ balance: 7 }) };
      }
      return { ok: true, json: async () => ({ available: true }) };
    });

    const result = await load({
      parent: async () => ({ isAuthenticated: true }),
      fetch: fetchMock,
      cookies: cookieJar('session-token')
    } as any);

    expect(result).toEqual({
      pods: [{ id: 'pod-1' }],
      balance: 7,
      availability: { available: true },
      nodeIp: '10.0.0.5'
    });
  });
});
