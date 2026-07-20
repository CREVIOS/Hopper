import { describe, expect, it, vi } from 'vitest';

vi.mock('$lib/api/server', () => ({
  apiUrl: (path: string) => `http://api.test${path}`
}));

function cookieJar(token?: string) {
  return {
    get(name: string) {
      return name === 'session_token' ? token : undefined;
    }
  };
}

describe('admin page server load', () => {
  it('redirects anonymous users to login', async () => {
    const { load } = await import('./+page.server');

    await expect(
      load({
        parent: async () => ({ isAuthenticated: false, user: null })
      } as any)
    ).rejects.toMatchObject({
      status: 302,
      location: '/login'
    });
  });

  it('redirects non-admin users to the dashboard', async () => {
    const { load } = await import('./+page.server');

    await expect(
      load({
        parent: async () => ({ isAuthenticated: true, user: { role: 'student' } })
      } as any)
    ).rejects.toMatchObject({
      status: 302,
      location: '/dashboard'
    });
  });

  it('returns the admin datasets for admin users', async () => {
    const { load } = await import('./+page.server');
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith('/admin/stats')) {
        return { ok: true, json: async () => ({ total_users: 10, active_vms: 2, total_vms_created: 25 }) };
      }
      if (url.endsWith('/admin/nodes')) {
        return { ok: true, json: async () => [{ name: 'node-1' }] };
      }
      if (url.endsWith('/admin/users')) {
        return { ok: true, json: async () => [{ id: 'user-1' }] };
      }
      if (url.endsWith('/admin/active-vms')) {
        return { ok: true, json: async () => [{ id: 'pod-1' }] };
      }
      if (url.endsWith('/admin/audit-logs?limit=500')) {
        return { ok: true, json: async () => [{ id: 'audit-1' }] };
      }
      if (url.endsWith('/issues/admin')) {
        return { ok: true, json: async () => [{ id: 'issue-1' }] };
      }
      if (url.endsWith('/admin/plans')) {
        return { ok: true, json: async () => [{ name: 'small' }] };
      }
      if (url.endsWith('/admin/images')) {
        return { ok: true, json: async () => [{ template: 'ubuntu' }] };
      }
      return { ok: true, json: async () => [{ id: 'req-1' }] };
    });

    const result = await load({
      parent: async () => ({ isAuthenticated: true, user: { id: 'admin-1', role: 'admin' } }),
      fetch: fetchMock,
      cookies: cookieJar('session-token')
    } as any);

    expect(result).toEqual({
      currentUserId: 'admin-1',
      currentUserRole: 'admin',
      stats: { total_users: 10, active_vms: 2, total_vms_created: 25 },
      nodes: [{ name: 'node-1' }],
      users: [{ id: 'user-1' }],
      activeVms: [{ id: 'pod-1' }],
      auditLogs: [{ id: 'audit-1' }],
      teacherRequests: [{ id: 'req-1' }],
      issues: [{ id: 'issue-1' }],
      plans: [{ name: 'small' }],
      images: [{ template: 'ubuntu' }]
    });
  });
});
