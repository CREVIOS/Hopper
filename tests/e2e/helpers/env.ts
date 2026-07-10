function parseBoolean(value: string | undefined): boolean {
  return /^(1|true|yes)$/i.test(value ?? '');
}

export const e2eEnv = {
  baseURL: process.env.BASE_URL ?? 'http://127.0.0.1:5173',
  adminEmail: process.env.E2E_ADMIN_EMAIL,
  adminPassword: process.env.E2E_ADMIN_PASSWORD,
  studentEmail: process.env.E2E_STUDENT_EMAIL,
  studentPassword: process.env.E2E_STUDENT_PASSWORD,
  devAdminPassword: process.env.DEV_LOGIN_PASS,
  devStudentPassword: process.env.DEV_LOGIN_PASS_ALT,
  allowMutations: parseBoolean(process.env.E2E_ALLOW_MUTATIONS),
  crossBrowser: parseBoolean(process.env.E2E_CROSS_BROWSER)
};

export type AuthRole = 'admin' | 'student';
export type AuthMode = 'password' | 'dev-login' | 'missing';

export function resolveAuthMode(role: AuthRole): AuthMode {
  if (role === 'admin') {
    if (e2eEnv.adminEmail && e2eEnv.adminPassword) return 'password';
    if (e2eEnv.devAdminPassword) return 'dev-login';
    return 'missing';
  }

  if (e2eEnv.studentEmail && e2eEnv.studentPassword) return 'password';
  if (e2eEnv.devStudentPassword) return 'dev-login';
  return 'missing';
}

export function hasAuth(role: AuthRole): boolean {
  return resolveAuthMode(role) !== 'missing';
}

export function authRequirementMessage(role: AuthRole): string {
  if (role === 'admin') {
    return 'Admin auth requires E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD or DEV_LOGIN_PASS.';
  }

  return 'Student auth requires E2E_STUDENT_EMAIL/E2E_STUDENT_PASSWORD or DEV_LOGIN_PASS_ALT.';
}
