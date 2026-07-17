import { afterEach, describe, expect, it, vi } from 'vitest';

async function importClient() {
  vi.resetModules();
  return import('./client');
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('api client', () => {
  it('retries once after a successful refresh', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'expired' }), { status: 401 })
      )
      .mockResolvedValueOnce(new Response(null, { status: 200 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ pods: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      );

    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('window', { location: { href: '' } });

    const { api } = await importClient();
    const result = await api.get<{ pods: unknown[] }>('/pods');

    expect(result).toEqual({ pods: [] });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/auth/refresh');
  });

  it('does not attempt refresh for invalid login credentials', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Invalid email or password.' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' }
      })
    );

    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('window', { location: { href: '' } });

    const { api, ApiError } = await importClient();

    await expect(api.post('/auth/login', { email: 'student@example.edu' })).rejects.toMatchObject({
      name: ApiError.name,
      status: 401,
      message: 'Invalid email or password.'
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('redirects to login when refresh fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('expired', { status: 401 }))
      .mockResolvedValueOnce(new Response('no refresh', { status: 401 }));
    const location = { href: '' };

    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('window', { location });

    const { api, ApiError } = await importClient();

    await expect(api.get('/credits/balance')).rejects.toMatchObject({
      name: ApiError.name,
      status: 401,
      message: 'Session expired'
    });
    expect(location.href).toBe('/login');
  });
});
