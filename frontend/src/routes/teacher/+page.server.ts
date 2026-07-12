import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { apiUrl } from '$lib/api/server';

export const load: PageServerLoad = async ({ parent, fetch, cookies }) => {
  const { isAuthenticated, user } = await parent();
  if (!isAuthenticated) {
    redirect(302, '/login');
  }
  // Teacher console is for professors; admins fund teachers from /admin.
  if (user?.role !== 'professor') {
    redirect(302, '/dashboard');
  }

  const token = cookies.get('session_token');
  const headers: Record<string, string> = token ? { Cookie: `session_token=${token}` } : {};

  const [balanceRes, studentsRes, coursesRes] = await Promise.all([
    fetch(apiUrl('/credits/balance'), { headers }).catch(() => null),
    fetch(apiUrl('/credits/students'), { headers }).catch(() => null),
    fetch(apiUrl('/courses/mine'), { headers }).catch(() => null)
  ]);

  const balance = balanceRes?.ok ? (await balanceRes.json()).balance ?? 0 : 0;
  const students = studentsRes?.ok ? await studentsRes.json() : [];
  const courses = coursesRes?.ok ? await coursesRes.json() : [];

  return { balance, students, courses, currentUserId: user?.id ?? '' };
};
