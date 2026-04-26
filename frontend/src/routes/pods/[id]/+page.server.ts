import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { apiUrl } from '$lib/api/server';
import { env } from '$env/dynamic/private';

export const load: PageServerLoad = async ({ parent, params, fetch, cookies }) => {
  const { isAuthenticated } = await parent();
  if (!isAuthenticated) {
    redirect(302, '/login');
  }

  const token = cookies.get('session_token');
  const headers: Record<string, string> = token
    ? { Cookie: `session_token=${token}` }
    : {};

  const res = await fetch(apiUrl(`/pods/${params.id}`), { headers }).catch(() => null);
  const pod = res?.ok ? await res.json() : null;

  // NODE_IP is set in .env — the external IP of your K8s node.
  // NodePort services (SSH, VS Code) are accessed via this IP.
  return { pod, nodeIp: env.NODE_IP ?? '127.0.0.1' };
};
