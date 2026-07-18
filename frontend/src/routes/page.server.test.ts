import { describe, expect, it } from 'vitest';

describe('root page server load', () => {
  it('redirects authenticated users to the dashboard', async () => {
    const { load } = await import('./+page.server');

    await expect(
      load({
        parent: async () => ({ isAuthenticated: true })
      } as any)
    ).rejects.toMatchObject({
      status: 302,
      location: '/dashboard'
    });
  });

  it('shows the landing page to anonymous users', async () => {
    const { load } = await import('./+page.server');

    // Anonymous visitors see the public landing page (a plain load result),
    // not a redirect — only authenticated users are bounced to /dashboard.
    await expect(
      load({
        parent: async () => ({ isAuthenticated: false })
      } as any)
    ).resolves.toEqual({});
  });
});
