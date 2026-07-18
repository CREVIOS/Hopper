import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { apiUrl } from '$lib/api/server';
import { env } from '$env/dynamic/private';

export const load: PageServerLoad = async ({ parent, fetch, cookies }) => {
  const { isAuthenticated } = await parent();
  if (!isAuthenticated) {
    redirect(302, '/login');
  }

  const token = cookies.get('session_token');
  const headers: Record<string, string> = token
    ? { Cookie: `session_token=${token}` }
    : {};

  const [podsRes, balanceRes, plansRes, availabilityRes] = await Promise.all([
    fetch(apiUrl('/pods/'), { headers }).catch(() => null),
    fetch(apiUrl('/credits/balance'), { headers }).catch(() => null),
    fetch(apiUrl('/pods/plans'), { headers }).catch(() => null),
    fetch(apiUrl('/pods/availability'), { headers }).catch(() => null)
  ]);

  const pods = podsRes?.ok ? await podsRes.json() : [];
  const balance = balanceRes?.ok ? (await balanceRes.json()).balance : 0;
  // Best-effort: the availability endpoint never 500s, but the fetch itself can
  // still fail (network / orchestrator down) — fall back to null so the readout
  // renders placeholders instead of breaking the page.
  const availability = availabilityRes?.ok ? await availabilityRes.json() : null;

  // The plan catalogue is a { name: {...} } map; flatten to a sorted array for
  // the picker. Empty on failure — the page falls back to its static list.
  const plansObj: Record<string, Record<string, unknown>> = plansRes?.ok
    ? await plansRes.json()
    : {};
  const plans = Object.entries(plansObj)
    .sort(([, a], [, b]) => Number(a.credits_per_hour) - Number(b.credits_per_hour))
    .map(([name, v]) => ({ name, ...v }));

  return {
    pods,
    balance,
    plans,
    availability,
    nodeIp: env.NODE_IP ?? '127.0.0.1'
  };
};
