import type { LayoutServerLoad } from './$types';
import { apiUrl } from '$lib/api/server';

// Try /auth/me with the given session token; return parsed user or null on 401.
async function fetchUser(fetch: typeof globalThis.fetch, token: string) {
  const res = await fetch(apiUrl('/auth/me'), {
    headers: { Cookie: `session_token=${token}` }
  });
  if (res.ok) return await res.json();
  return null;
}

async function fetchBalance(
  fetch: typeof globalThis.fetch,
  token: string
): Promise<number | null> {
  try {
    const res = await fetch(apiUrl('/credits/balance'), {
      headers: { Cookie: `session_token=${token}` }
    });
    if (!res.ok) return null;
    const json = await res.json();
    return typeof json?.balance === 'number' ? json.balance : null;
  } catch {
    return null;
  }
}

export const load: LayoutServerLoad = async ({ cookies, fetch }) => {
  const token = cookies.get('session_token');
  const refresh = cookies.get('refresh_token');

  if (token) {
    try {
      const user = await fetchUser(fetch, token);
      if (user) {
        const balance = await fetchBalance(fetch, token);
        return { isAuthenticated: true, user, balance };
      }
    } catch {
      // fall through to refresh attempt
    }
  }

  // Access token missing/expired — try the refresh token before giving up.
  // The api-gateway's /auth/refresh issues new Set-Cookie headers; we forward
  // them so the browser keeps a valid session.
  if (refresh) {
    try {
      const refreshRes = await fetch(apiUrl('/auth/refresh'), {
        method: 'POST',
        headers: { Cookie: `refresh_token=${refresh}` }
      });
      if (refreshRes.ok) {
        const setCookies = refreshRes.headers.getSetCookie?.() ?? [];
        let newToken = '';
        for (const c of setCookies) {
          const m = c.match(/^session_token=([^;]+)/);
          if (m) newToken = m[1];
          const [pair, ...attrs] = c.split(';').map((s) => s.trim());
          const [name, value] = pair.split('=');
          const attrMap: Record<string, string> = {};
          for (const a of attrs) {
            const [k, v] = a.split('=');
            attrMap[k.toLowerCase()] = v ?? '';
          }
          cookies.set(name, value, {
            path: attrMap['path'] || '/',
            httpOnly: 'httponly' in attrMap,
            secure: 'secure' in attrMap,
            sameSite:
              (attrMap['samesite']?.toLowerCase() as 'lax' | 'strict' | 'none') ||
              'none',
            maxAge: attrMap['max-age'] ? Number(attrMap['max-age']) : undefined
          });
        }
        if (newToken) {
          const user = await fetchUser(fetch, newToken);
          if (user) {
            const balance = await fetchBalance(fetch, newToken);
            return { isAuthenticated: true, user, balance };
          }
        }
      }
    } catch {
      // refresh failed; treat as logged out
    }
  }

  return { isAuthenticated: false, user: null, balance: null };
};
