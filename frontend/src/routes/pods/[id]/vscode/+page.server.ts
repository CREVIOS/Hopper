import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { apiUrl } from '$lib/api/server';

export const load: PageServerLoad = async ({ parent, params, fetch, cookies }) => {
  const { isAuthenticated, user } = await parent();
  if (!isAuthenticated) {
    redirect(302, '/login');
  }

  const token = cookies.get('session_token');
  const headers: Record<string, string> = token
    ? { Cookie: `session_token=${token}` }
    : {};

  const res = await fetch(apiUrl(`/pods/${params.id}`), { headers }).catch(() => null);
  const pod = res?.ok ? await res.json() : null;

  return { pod, userId: user?.id ?? '' };
};
