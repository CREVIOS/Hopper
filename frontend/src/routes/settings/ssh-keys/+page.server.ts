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

  const [sshRes, apiRes] = await Promise.all([
    fetch(apiUrl('/ssh-keys/'), { headers }).catch(() => null),
    fetch(apiUrl('/auth/api-keys'), { headers }).catch(() => null)
  ]);
  const keys = sshRes?.ok ? await sshRes.json() : [];
  const apiKeys = apiRes?.ok ? await apiRes.json() : [];

  return { keys, apiKeys };
};
