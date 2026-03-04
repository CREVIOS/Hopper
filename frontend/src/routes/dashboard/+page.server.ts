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

  const [balanceRes, podsRes] = await Promise.all([
    fetch('/api/credits/balance', { headers }).catch(() => null),
    fetch('/api/pods', { headers }).catch(() => null)
  ]);

  const balance = balanceRes?.ok ? (await balanceRes.json()).balance : 0;
  const pods = podsRes?.ok ? await podsRes.json() : [];

  return { balance, pods };
};
