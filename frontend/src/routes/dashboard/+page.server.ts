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

  const [balanceRes, podsRes, historyRes, summaryRes] = await Promise.all([
    fetch(apiUrl('/credits/balance'), { headers }).catch(() => null),
    fetch(apiUrl('/pods/'), { headers }).catch(() => null),
    fetch(apiUrl('/credits/history?limit=5'), { headers }).catch(() => null),
    fetch(apiUrl('/usage/summary/me'), { headers }).catch(() => null)
  ]);

  const balance = balanceRes?.ok ? (await balanceRes.json()).balance : 0;
  const pods = podsRes?.ok ? await podsRes.json() : [];
  const recent = historyRes?.ok ? await historyRes.json() : [];
  const summary = summaryRes?.ok
    ? await summaryRes.json()
    : { pod_count: 0, avg_cpu_percent: 0, avg_memory_bytes: 0 };

  return { balance, pods, recent, summary };
};
