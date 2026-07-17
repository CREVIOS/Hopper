function parseBoolean(value: string | undefined): boolean {
  return /^(1|true|yes)$/i.test(value ?? '');
}

export const e2eEnv = {
  baseURL: process.env.BASE_URL ?? 'http://127.0.0.1:5173',
  controlURL:
    process.env.E2E_CONTROL_URL ??
    `http://127.0.0.1:${process.env.E2E_CONTROL_PORT ?? '8000'}`,
  adminEmail: process.env.E2E_ADMIN_EMAIL ?? 'admin@test.edu',
  adminPassword: process.env.E2E_ADMIN_PASSWORD ?? 'e2e',
  professorEmail: process.env.E2E_PROFESSOR_EMAIL ?? 'professor@test.edu',
  professorPassword: process.env.E2E_PROFESSOR_PASSWORD ?? 'e2e',
  studentEmail: process.env.E2E_STUDENT_EMAIL ?? 'student-1@test.edu',
  studentPassword: process.env.E2E_STUDENT_PASSWORD ?? 'e2e',
  devAdminPassword: process.env.DEV_LOGIN_PASS ?? 'e2e',
  devStudentPassword: process.env.DEV_LOGIN_PASS_ALT ?? 'e2e',
  allowMutations: parseBoolean(process.env.E2E_ALLOW_MUTATIONS),
  crossBrowser: parseBoolean(process.env.E2E_CROSS_BROWSER),
  useMockServer: !/^(0|false|no)$/i.test(process.env.E2E_USE_MOCK_SERVER ?? 'true')
};

export type AuthRole = 'admin' | 'professor' | 'student';
export type AuthMode = 'password' | 'dev-login' | 'missing';

export function resolveAuthMode(role: AuthRole): AuthMode {
  if (role === 'admin') {
    if (e2eEnv.devAdminPassword) return 'dev-login';
    if (e2eEnv.adminEmail && e2eEnv.adminPassword) return 'password';
    return 'missing';
  }

  if (role === 'professor') {
    if (e2eEnv.professorEmail && e2eEnv.professorPassword) return 'password';
    return 'missing';
  }

  if (e2eEnv.devStudentPassword) return 'dev-login';
  if (e2eEnv.studentEmail && e2eEnv.studentPassword) return 'password';
  return 'missing';
}

export function hasAuth(role: AuthRole): boolean {
  return resolveAuthMode(role) !== 'missing';
}

export function authRequirementMessage(role: AuthRole): string {
  if (role === 'admin') {
    return 'Admin auth requires E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD or DEV_LOGIN_PASS.';
  }

  if (role === 'professor') {
    return 'Professor auth requires E2E_PROFESSOR_EMAIL/E2E_PROFESSOR_PASSWORD.';
  }

  return 'Student auth requires E2E_STUDENT_EMAIL/E2E_STUDENT_PASSWORD or DEV_LOGIN_PASS_ALT.';
}
