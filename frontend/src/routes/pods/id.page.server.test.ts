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
  return import('./[id]/+page.server');
}

afterEach(() => {
  vi.resetModules();
  vi.unmock('$env/dynamic/private');
});

describe('pod detail page server load', () => {
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

  it('returns the pod and node IP for authenticated users', async () => {
    const { load } = await importPage('10.0.0.9');
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ id: 'pod-42', state: 'running' })
    }));

    const result = await load({
      parent: async () => ({ isAuthenticated: true }),
      params: { id: 'pod-42' },
      fetch: fetchMock,
      cookies: cookieJar('session-token')
    } as any);

    expect(result).toEqual({
      pod: { id: 'pod-42', state: 'running' },
      nodeIp: '10.0.0.9'
    });
  });
});
