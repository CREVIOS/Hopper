import { get } from 'svelte/store';
import { describe, expect, it } from 'vitest';

import { isAuthenticated, user } from './auth';

describe('auth stores', () => {
  it('default to a logged-out state', () => {
    user.set(null);
    isAuthenticated.set(false);

    expect(get(user)).toBeNull();
    expect(get(isAuthenticated)).toBe(false);
  });

  it('store the authenticated user and flag together', () => {
    const currentUser = {
      id: 'user-1',
      email: 'student@example.edu',
      name: 'Student Example',
      role: 'student' as const,
      email_verified: true,
      pending_teacher: false
    };

    user.set(currentUser);
    isAuthenticated.set(true);

    expect(get(user)).toEqual(currentUser);
    expect(get(isAuthenticated)).toBe(true);
  });
});
