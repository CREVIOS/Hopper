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

  it('allows anonymous users to see the landing page', async () => {
    const { load } = await import('./+page.server');

    await expect(
      load({
        parent: async () => ({ isAuthenticated: false })
      } as any)
    ).resolves.toEqual({});
  });
});
