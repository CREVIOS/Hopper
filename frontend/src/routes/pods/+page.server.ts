import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ parent, fetch, cookies }) => {
  const { isAuthenticated } = await parent();
  if (!isAuthenticated) {
    redirect(302, '/login');
  }

  const token = cookies.get('session_token');
  const headers: Record<string, string> = token
    ? { Cookie: `session_token=${token}` }
    : {};

  const res = await fetch('/api/pods', { headers }).catch(() => null);
  const pods = res?.ok ? await res.json() : [];

  return { pods };
};
