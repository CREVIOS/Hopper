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

describe('teacher page server load', () => {
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

  it('redirects non-professors to the dashboard', async () => {
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

  it('returns teacher balance and students for professors', async () => {
    const { load } = await import('./+page.server');
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith('/credits/balance')) {
        return { ok: true, json: async () => ({ balance: 12 }) };
      }
      return { ok: true, json: async () => [{ id: 'student-1' }] };
    });

    const result = await load({
      parent: async () => ({ isAuthenticated: true, user: { id: 'teacher-1', role: 'professor' } }),
      fetch: fetchMock,
      cookies: cookieJar('session-token')
    } as any);

    expect(result).toEqual({
      balance: 12,
      students: [{ id: 'student-1' }],
      currentUserId: 'teacher-1'
    });
  });
});
