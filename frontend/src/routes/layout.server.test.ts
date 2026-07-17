import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('$lib/api/server', () => ({
  apiUrl: (path: string) => `http://api.test${path}`
}));

afterEach(() => {
  vi.clearAllMocks();
});

function makeCookies(values: Record<string, string | undefined>) {
  const writes: Array<{ name: string; value: string; options: Record<string, unknown> }> = [];

  return {
    writes,
    jar: {
      get(name: string) {
        return values[name];
      },
      set(name: string, value: string, options: Record<string, unknown>) {
        writes.push({ name, value, options });
      }
    }
  };
}

describe('root layout server load', () => {
  it('returns logged-out state without cookies', async () => {
    const { load } = await import('./+layout.server');
    const cookies = makeCookies({});

    const result = await load({
      cookies: cookies.jar,
      fetch: vi.fn()
    } as any);

    expect(result).toEqual({
      isAuthenticated: false,
      user: null,
      balance: null
    });
  });

  it('returns the current user and balance with a valid session token', async () => {
    const { load } = await import('./+layout.server');
    const cookies = makeCookies({ session_token: 'access-token' });
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith('/auth/me')) {
        return {
          ok: true,
          json: async () => ({ id: 'user-1', role: 'student' })
        };
      }
      return {
        ok: true,
        json: async () => ({ balance: 12.5 })
      };
    });

    const result = await load({
      cookies: cookies.jar,
      fetch: fetchMock
    } as any);

    expect(result).toEqual({
      isAuthenticated: true,
      user: { id: 'user-1', role: 'student' },
      balance: 12.5
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('refreshes the session and forwards cookies before retrying auth', async () => {
    const { load } = await import('./+layout.server');
    const cookies = makeCookies({ refresh_token: 'refresh-token' });
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith('/auth/refresh')) {
        return {
          ok: true,
          headers: {
            getSetCookie: () => [
              'session_token=new-token; Path=/; HttpOnly; Secure; SameSite=None; Max-Age=300',
              'refresh_token=new-refresh; Path=/; HttpOnly; Secure; SameSite=None; Max-Age=1800'
            ]
          }
        };
      }

      if (url.endsWith('/auth/me')) {
        return {
          ok: true,
          json: async () => ({ id: 'user-2', role: 'admin' })
        };
      }

      return {
        ok: true,
        json: async () => ({ balance: 99 })
      };
    });

    const result = await load({
      cookies: cookies.jar,
      fetch: fetchMock
    } as any);

    expect(result).toEqual({
      isAuthenticated: true,
      user: { id: 'user-2', role: 'admin' },
      balance: 99
    });
    expect(cookies.writes.map((entry) => entry.name)).toEqual([
      'session_token',
      'refresh_token'
    ]);
  });
});
