import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ parent }) => {
  const { isAuthenticated } = await parent();
  // Signed-in users go straight to the app; everyone else sees the landing page.
  if (isAuthenticated) {
    redirect(302, '/dashboard');
  }
  return {};
};
