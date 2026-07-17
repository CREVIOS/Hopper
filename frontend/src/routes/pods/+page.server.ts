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

  const [podsRes, balanceRes, availabilityRes] = await Promise.all([
    fetch(apiUrl('/pods/'), { headers }).catch(() => null),
    fetch(apiUrl('/credits/balance'), { headers }).catch(() => null),
    fetch(apiUrl('/pods/availability'), { headers }).catch(() => null)
  ]);

  const pods = podsRes?.ok ? await podsRes.json() : [];
  const balance = balanceRes?.ok ? (await balanceRes.json()).balance : 0;
  // Best-effort: the availability endpoint never 500s, but the fetch itself can
  // still fail (network / orchestrator down) — fall back to null so the readout
  // renders placeholders instead of breaking the page.
  const availability = availabilityRes?.ok ? await availabilityRes.json() : null;

  return {
    pods,
    balance,
    availability,
    nodeIp: env.NODE_IP ?? '127.0.0.1'
  };
};
