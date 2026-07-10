import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { apiUrl } from '$lib/api/server';

export const load: PageServerLoad = async ({ parent, fetch, cookies }) => {
  const { isAuthenticated, user } = await parent();
  if (!isAuthenticated) {
    redirect(302, '/login');
  }
  // Admin panel is admin-only. Teachers (professors) get the Teaching console
  // instead and are bounced back to their dashboard here.
  if (user?.role !== 'admin') {
    redirect(302, '/dashboard');
  }

  const token = cookies.get('session_token');
  const headers: Record<string, string> = token
    ? { Cookie: `session_token=${token}` }
    : {};

  const [statsRes, nodesRes, usersRes, activeVmsRes, auditRes, reqRes] = await Promise.all([
    fetch(apiUrl('/admin/stats'), { headers }).catch(() => null),
    fetch(apiUrl('/admin/nodes'), { headers }).catch(() => null),
    fetch(apiUrl('/admin/users'), { headers }).catch(() => null),
    fetch(apiUrl('/admin/active-vms'), { headers }).catch(() => null),
    fetch(apiUrl('/admin/audit-logs?limit=500'), { headers }).catch(() => null),
    fetch(apiUrl('/admin/teacher-requests'), { headers }).catch(() => null)
  ]);

  const stats = statsRes?.ok ? await statsRes.json() : { total_users: 0, active_vms: 0, total_vms_created: 0 };
  const nodes = nodesRes?.ok ? await nodesRes.json() : [];
  const users = usersRes?.ok ? await usersRes.json() : [];
  const activeVms = activeVmsRes?.ok ? await activeVmsRes.json() : [];
  const auditLogs = auditRes?.ok ? await auditRes.json() : [];
  const teacherRequests = reqRes?.ok ? await reqRes.json() : [];

  return {
    currentUserId: user?.id ?? '',
    currentUserRole: user?.role ?? '',
    stats,
    nodes,
    users,
    activeVms,
    auditLogs,
    teacherRequests,
  };
};
