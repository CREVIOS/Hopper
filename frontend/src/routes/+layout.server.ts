import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ cookies }) => {
  const token = cookies.get('session_token');
  return {
    isAuthenticated: !!token
  };
};
