import { describe, expect, it } from 'vitest';

describe('settings page server load', () => {
  it('redirects to ssh key settings', async () => {
    const { load } = await import('./+page.server');

    await expect(load({} as any)).rejects.toMatchObject({
      status: 302,
      location: '/settings/ssh-keys'
    });
  });
});
