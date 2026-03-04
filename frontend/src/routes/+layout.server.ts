import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ cookies, fetch }) => {
  const token = cookies.get('session_token');
  if (!token) {
    return { isAuthenticated: false, user: null };
  }

  try {
    const res = await fetch('/api/auth/me', {
      headers: { Cookie: `session_token=${token}` }
    });
    if (res.ok) {
      const user = await res.json();
      return { isAuthenticated: true, user };
    }
  } catch {
    // Token invalid or API unreachable
  }

  return { isAuthenticated: true, user: null };
};
