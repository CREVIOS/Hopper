import { afterEach, describe, expect, it, vi } from 'vitest';

async function importRoute(options?: {
  dev?: boolean;
  env?: Record<string, string | undefined>;
}) {
  vi.resetModules();
  vi.doMock('$app/environment', () => ({ dev: options?.dev ?? true }));
  vi.doMock('$env/dynamic/private', () => ({ env: options?.env ?? {} }));
  return import('./+server');
}

function cookieJar() {
  const writes: Array<{ name: string; value: string; options: Record<string, unknown> }> = [];
  return {
    writes,
    jar: {
      set(name: string, value: string, options: Record<string, unknown>) {
        writes.push({ name, value, options });
      }
    }
  };
}

afterEach(() => {
  vi.resetModules();
  vi.unmock('$app/environment');
  vi.unmock('$env/dynamic/private');
  vi.restoreAllMocks();
});

describe('dev login route', () => {
  it('returns 404 outside development builds', async () => {
    const { GET } = await importRoute({ dev: false });

    await expect(
      GET({
        cookies: cookieJar().jar
      } as any)
    ).rejects.toMatchObject({
      status: 404,
      body: { message: 'Not found' }
    });
  });

  it('redirects back to login when the token request fails', async () => {
    const { GET } = await importRoute();
    const cookies = cookieJar();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: vi.fn().mockResolvedValue('invalid_grant')
    });

    await expect(
      GET({
        cookies: cookies.jar,
        fetch: fetchMock,
        url: new URL('http://localhost/dev-login')
      } as any)
    ).rejects.toMatchObject({
      status: 303,
      location: '/login?error=devlogin'
    });

    expect(fetchMock).toHaveBeenCalledWith(
      'https://hopper.farefin.com/realms/hopper/protocol/openid-connect/token',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      })
    );
    expect(cookies.writes).toHaveLength(0);
  });

  it('sets auth cookies and redirects to the dashboard on success', async () => {
    const { GET } = await importRoute({
      env: {
        KEYCLOAK_EXTERNAL_URL: 'https://kc.example.com/',
        KEYCLOAK_REALM: 'test-realm',
        KEYCLOAK_CLIENT_ID: 'frontend-client',
        KEYCLOAK_CLIENT_SECRET: 'super-secret',
        DEV_LOGIN_USER_ALT: 'student-default',
        DEV_LOGIN_PASS_ALT: 'student-pass'
      }
    });
    const cookies = cookieJar();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        access_token: 'access-token',
        refresh_token: 'refresh-token',
        id_token: 'id-token',
        expires_in: 120,
        refresh_expires_in: 900
      })
    });

    await expect(
      GET({
        cookies: cookies.jar,
        fetch: fetchMock,
        url: new URL('http://localhost/dev-login?as=user&user=override-user&pass=override-pass')
      } as any)
    ).rejects.toMatchObject({
      status: 303,
      location: '/dashboard'
    });

    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(request.body).toBeInstanceOf(URLSearchParams);
    const body = request.body as URLSearchParams;
    expect(body.get('client_id')).toBe('frontend-client');
    expect(body.get('client_secret')).toBe('super-secret');
    expect(body.get('username')).toBe('override-user');
    expect(body.get('password')).toBe('override-pass');
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      'https://kc.example.com/realms/test-realm/protocol/openid-connect/token'
    );

    expect(cookies.writes.map((entry) => entry.name)).toEqual([
      'session_token',
      'refresh_token',
      'id_token'
    ]);
    expect(cookies.writes[0]).toMatchObject({
      value: 'access-token',
      options: expect.objectContaining({
        path: '/',
        httpOnly: true,
        secure: false,
        sameSite: 'lax',
        maxAge: 120
      })
    });
    expect(cookies.writes[2]).toMatchObject({
      value: 'id-token',
      options: expect.objectContaining({
        maxAge: 900
      })
    });
  });
});
