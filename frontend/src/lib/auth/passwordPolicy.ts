/**
 * Mirror of the Keycloak `hopper` realm password policy, for the UI.
 *
 * The gateway (app/services/password_policy.py) is authoritative and rejects a
 * non-compliant password with a 400 naming every unmet rule. This copy exists
 * so the requirements can be listed *before* the user picks a password, and so
 * a bad one is caught without a round trip. Wording is kept identical to the
 * gateway's so the checklist and the server error never contradict each other
 * (passwordPolicy.test.ts pins the exact sentences).
 *
 * Keep in sync with scripts/keycloak-harden.sh:
 *
 *     length(12) and digits(1) and lowerCase(1) and upperCase(1)
 *     and notUsername(undefined) and passwordHistory(3)
 *
 * `passwordHistory(3)` is absent by design — only Keycloak knows previous
 * passwords, so reuse surfaces as a 400 from the gateway instead.
 */

export const MIN_LENGTH = 12;

export interface PasswordRule {
  readonly id: string;
  /** Checklist copy, e.g. "At least 12 characters". */
  readonly text: string;
  /** Noun phrase folded into "Password must contain <a and b>." */
  readonly clause?: string;
  /** Standalone sentence for rules that don't read as a "contain" clause. */
  readonly sentence?: string;
  readonly test: (password: string, username: string) => boolean;
}

export const PASSWORD_RULES: readonly PasswordRule[] = [
  {
    id: 'length',
    text: `At least ${MIN_LENGTH} characters`,
    clause: `at least ${MIN_LENGTH} characters`,
    test: (pw) => pw.length >= MIN_LENGTH
  },
  // Unicode-aware, not /[a-z]/ — Keycloak uses Java's Character.isDigit /
  // isLowerCase / isUpperCase, which accept non-ASCII. ASCII-only tests here
  // would tell a user that "Ábcdefghij1" has no uppercase while the gateway
  // and the realm both accept it, leaving the checklist unsatisfiable.
  {
    id: 'digits',
    text: 'At least one digit (0-9)',
    clause: 'at least one digit',
    test: (pw) => /\p{Nd}/u.test(pw)
  },
  {
    id: 'lowercase',
    text: 'At least one lowercase letter (a-z)',
    clause: 'at least one lowercase letter',
    test: (pw) => /\p{Ll}/u.test(pw)
  },
  {
    id: 'uppercase',
    text: 'At least one uppercase letter (A-Z)',
    clause: 'at least one uppercase letter',
    test: (pw) => /\p{Lu}/u.test(pw)
  },
  {
    id: 'not_username',
    text: 'Different from your email address',
    sentence: 'Password must not be the same as your email address.',
    // The gateway enforces this rule itself — Keycloak declares notUsername
    // but never actually fires it on the admin API (it lower-cases usernames,
    // so an equal password can't also satisfy upperCase(1)). Equality only,
    // never containment. See app/services/password_policy.py.
    test: (pw, username) =>
      !username || pw.trim().toLowerCase() !== username.trim().toLowerCase()
  }
];

/** Rules `password` does not satisfy, in declaration order. */
export function unmetRules(password: string, username: string): PasswordRule[] {
  return PASSWORD_RULES.filter((rule) => !rule.test(password, username));
}

export function isCompliant(password: string, username: string): boolean {
  return unmetRules(password, username).length === 0;
}

/** User-facing copy naming every unmet rule; '' when compliant. */
export function explainFailures(rules: readonly PasswordRule[]): string {
  const sentences: string[] = [];
  const clauses = rules.map((r) => r.clause).filter((c): c is string => !!c);
  if (clauses.length > 0) {
    sentences.push(`Password must contain ${joinClauses(clauses)}.`);
  }
  for (const rule of rules) {
    if (rule.sentence) sentences.push(rule.sentence);
  }
  return sentences.join(' ');
}

/** Oxford-comma join: 'a', 'a and b', 'a, b, and c'. */
function joinClauses(parts: readonly string[]): string {
  if (parts.length === 1) return parts[0];
  if (parts.length === 2) return `${parts[0]} and ${parts[1]}`;
  return `${parts.slice(0, -1).join(', ')}, and ${parts[parts.length - 1]}`;
}
