import type { LayoutServerLoad } from './$types';
import { apiUrl } from '$lib/api/server';

export const load: LayoutServerLoad = async ({ cookies, fetch }) => {
  const token = cookies.get('session_token');
  if (!token) {
    return { isAuthenticated: false, user: null };
  }

  try {
    const res = await fetch(apiUrl('/auth/me'), {
      headers: { Cookie: `session_token=${token}` }
    });
    if (res.ok) {
      const user = await res.json();
      return { isAuthenticated: true, user };
    }
  } catch {
    // Token invalid or API unreachable
  }

  return { isAuthenticated: false, user: null };
};
