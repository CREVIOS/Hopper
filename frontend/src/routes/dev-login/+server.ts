import { dev } from '$app/environment';
import { env } from '$env/dynamic/private';
import { error, redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

/**
 * DEV-ONLY one-click login.
 *
 * The real OAuth button (/api/auth/login) cannot complete on localhost: the
 * deployed backend builds the Keycloak redirect_uri from its own host, so
 * Keycloak returns the browser to the REMOTE callback and sets the session
 * cookie on that domain — localhost never sees it.
 *
 * Here we do a Resource Owner Password grant directly against Keycloak and set
 * the same cookies the real /auth/callback would, so SSR loads and the Vite
 * /api proxy both authenticate against the remote backend. The token is a
 * stateless JWT validated via JWKS, so the remote API accepts it from any host.
 *
 * Guarded by `dev` — this handler 404s in any production build.
 */
export const GET: RequestHandler = async ({ cookies, fetch, url }) => {
  if (!dev) throw error(404, 'Not found');

  const kc = (env.KEYCLOAK_EXTERNAL_URL || 'https://hopper.farefin.com').replace(/\/$/, '');
  const realm = env.KEYCLOAK_REALM || 'hopper';
  const clientId = env.KEYCLOAK_CLIENT_ID || 'hopper-api';

  // Pick a credential profile. `?as=user` uses the regular (non-admin) account;
  // anything else defaults to admin. `?user=&pass=` still override everything for
  // ad-hoc accounts.
  const as = url.searchParams.get('as');
  const profile =
    as === 'user'
      ? { user: env.DEV_LOGIN_USER_ALT || 'testuser', pass: env.DEV_LOGIN_PASS_ALT || 'testuser123' }
      : { user: env.DEV_LOGIN_USER || 'admin', pass: env.DEV_LOGIN_PASS || 'admin123' };
  const username = url.searchParams.get('user') || profile.user;
  const password = url.searchParams.get('pass') || profile.pass;

  const body = new URLSearchParams({
    grant_type: 'password',
    client_id: clientId,
    username,
    password,
    scope: 'openid email profile'
  });
  if (env.KEYCLOAK_CLIENT_SECRET) body.set('client_secret', env.KEYCLOAK_CLIENT_SECRET);

  const res = await fetch(`${kc}/realms/${realm}/protocol/openid-connect/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    console.error('[dev-login] token request failed', res.status, detail);
    throw redirect(303, '/login?error=devlogin');
  }

  const tokens = await res.json();
  // secure:false because dev runs over http://localhost; httpOnly mirrors the
  // real cookies (browser still forwards them to SSR + the Vite proxy).
  const common = { path: '/', httpOnly: true, secure: false, sameSite: 'lax' as const };

  cookies.set('session_token', tokens.access_token, {
    ...common,
    maxAge: Number(tokens.expires_in ?? 300)
  });
  if (tokens.refresh_token) {
    cookies.set('refresh_token', tokens.refresh_token, {
      ...common,
      maxAge: Number(tokens.refresh_expires_in ?? 1800)
    });
  }
  if (tokens.id_token) {
    cookies.set('id_token', tokens.id_token, {
      ...common,
      maxAge: Number(tokens.refresh_expires_in ?? 1800)
    });
  }

  throw redirect(303, '/dashboard');
};
