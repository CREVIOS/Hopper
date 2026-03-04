import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ parent }) => {
  const { isAuthenticated } = await parent();
  if (isAuthenticated) {
    redirect(302, '/dashboard');
  } else {
    redirect(302, '/login');
  }
};
