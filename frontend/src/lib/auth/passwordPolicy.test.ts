import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { MIN_LENGTH, PASSWORD_RULES, explainFailures, isCompliant, unmetRules } from './passwordPolicy';

const EMAIL = 'jane@cs.du.ac.bd';
const GOOD = 'CorrectHorse9Battery';

interface Vector {
  name: string;
  password: string;
  username?: string;
  unmet: string[];
  message: string;
}

// Read rather than import: the fixture lives outside the Vite project root,
// and it is shared with the gateway's suite (tests/unit/services/test_password_policy.py).
const vectorsPath = fileURLToPath(
  new URL('../../../../tests/fixtures/password_policy_vectors.json', import.meta.url)
);
const vectors: { defaultUsername: string; cases: Vector[] } = JSON.parse(
  readFileSync(vectorsPath, 'utf-8')
);

describe('password policy mirror', () => {
  it('accepts a compliant password', () => {
    expect(unmetRules(GOOD, EMAIL)).toEqual([]);
    expect(isCompliant(GOOD, EMAIL)).toBe(true);
  });

  it('reports the missing case classes for an all-digit password', () => {
    // The bug report's password: 15 chars, so the old length-only check let it
    // through and Keycloak rejected it with an unexplained 502.
    const unmet = unmetRules('111111111111111', EMAIL).map(r => r.id);
    expect(unmet).toEqual(['lowercase', 'uppercase']);
    expect(isCompliant('111111111111111', EMAIL)).toBe(false);
  });

  it.each([
    ['nodigitsatallhere', ['digits', 'uppercase']],
    ['NOLOWERCASE12345', ['lowercase']],
    ['nouppercase12345', ['uppercase']],
    ['NoDigitsButCased', ['digits']],
    ['Ab1', ['length']]
  ])('reports the right unmet rules for %s', (password, expected) => {
    expect(unmetRules(password, EMAIL).map(r => r.id)).toEqual(expected);
  });

  it('accepts a password of exactly the minimum length', () => {
    const pw = 'Abcdefghij1k';
    expect(pw).toHaveLength(MIN_LENGTH);
    expect(isCompliant(pw, EMAIL)).toBe(true);
  });

  it('rejects a password equal to the email, case-insensitively', () => {
    expect(unmetRules(EMAIL, EMAIL).map(r => r.id)).toContain('not_username');
    expect(unmetRules('Jane@CS.du.ac.bd', EMAIL).map(r => r.id)).toContain('not_username');
  });

  it('allows a password that merely contains the email', () => {
    // notUsername forbids equality only — being stricter than the realm would
    // reject passwords Keycloak accepts.
    expect(unmetRules(`${EMAIL}AndMore99`, EMAIL).map(r => r.id)).not.toContain('not_username');
  });

  it('does not crash before an email has been typed', () => {
    expect(isCompliant(GOOD, '')).toBe(true);
  });

  it('treats non-ASCII letters as case, matching the gateway and the realm', () => {
    // Keycloak uses Java's Character.isUpperCase, which is Unicode-aware, and
    // the gateway mirrors it. An ASCII-only /[A-Z]/ here would tell the user
    // this password has no uppercase while the server accepts it — an
    // unsatisfiable checklist. See tests/unit/services/test_password_policy.py.
    expect(unmetRules('Ábcdefghij1k', EMAIL)).toEqual([]);
  });

  it('does not count a superscript two as a digit', () => {
    // Category No, not Nd — Keycloak rejects it, so the checklist must too.
    expect(unmetRules('abcdefghijkA²', EMAIL).map(r => r.id)).toContain('digits');
  });

  it('exposes every rule with human copy for the checklist', () => {
    expect(PASSWORD_RULES.map(r => r.id)).toEqual([
      'length',
      'digits',
      'lowercase',
      'uppercase',
      'not_username'
    ]);
    for (const rule of PASSWORD_RULES) {
      expect(rule.text.length).toBeGreaterThan(0);
    }
  });
});

describe('explainFailures', () => {
  it('names every unmet rule', () => {
    const msg = explainFailures(unmetRules('aaaaaaaaaaaa', EMAIL));
    expect(msg).toContain('digit');
    expect(msg).toContain('uppercase letter');
  });

  it('reads as one clause when a single rule fails', () => {
    const msg = explainFailures(unmetRules('aaaaaaaaaaaa1', EMAIL));
    expect(msg).toBe('Password must contain at least one uppercase letter.');
  });

  it('is empty for a compliant password', () => {
    expect(explainFailures(unmetRules(GOOD, EMAIL))).toBe('');
  });
});

describe('shared vectors with the gateway', () => {
  // The contract with services/api-gateway/app/services/password_policy.py.
  // Both mirrors assert against the same fixture, so a predicate or wording
  // change on either side fails the other's suite instead of quietly letting
  // this checklist and the server's error message disagree.
  it.each(vectors.cases)('$name', (vector) => {
    const username = vector.username ?? vectors.defaultUsername;

    const unmet = unmetRules(vector.password, username);

    expect(unmet.map((r) => r.id)).toEqual(vector.unmet);
    expect(explainFailures(unmet)).toBe(vector.message);
  });
});
