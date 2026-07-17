import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { apiUrl } from '$lib/api/server';

export const load: PageServerLoad = async ({ parent, fetch, cookies }) => {
  const { isAuthenticated } = await parent();
  if (!isAuthenticated) {
    redirect(302, '/login');
  }

  const token = cookies.get('session_token');
  const headers: Record<string, string> = token
    ? { Cookie: `session_token=${token}` }
    : {};

  const entriesRes = await fetch(apiUrl('/pods/queue'), { headers }).catch(
    () => null
  );
  // Best-effort: an unreachable API leaves the queue empty rather than 500ing.
  const entries = entriesRes?.ok ? await entriesRes.json() : [];

  return { entries };
};
