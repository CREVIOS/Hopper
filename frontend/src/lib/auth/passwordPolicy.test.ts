import { describe, expect, it } from 'vitest';
import { MIN_LENGTH, PASSWORD_RULES, explainFailures, isCompliant, unmetRules } from './passwordPolicy';

const EMAIL = 'jane@cs.du.ac.bd';
const GOOD = 'CorrectHorse9Battery';

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

  it('matches the gateway wording so client and server agree', () => {
    // app/services/password_policy.py renders the identical sentence.
    expect(explainFailures(unmetRules('111111111111111', EMAIL))).toBe(
      'Password must contain at least one lowercase letter and at least one uppercase letter.'
    );
    expect(explainFailures(unmetRules('Ab1', EMAIL))).toBe(
      'Password must contain at least 12 characters.'
    );
    expect(explainFailures(unmetRules(EMAIL, EMAIL))).toContain(
      'Password must not be the same as your email address.'
    );
  });

  it('is empty for a compliant password', () => {
    expect(explainFailures(unmetRules(GOOD, EMAIL))).toBe('');
  });
});
