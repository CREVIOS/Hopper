"""Mirror of the Keycloak `hopper` realm password policy.

Keycloak is the enforcer: it rejects a non-compliant password at create-user
and reset-password with a 400. But it only says so after a round trip, and the
gateway used to collapse that 400 into "Could not create the account. Try again
later." — which tells the user nothing about the real problem (see the
`length(12)`-only check that used to live in schemas/user.py).

Mirroring the rules here lets us:
  1. list the requirements in the UI *before* the user picks a password, and
  2. return a precise, itemised 400 naming exactly which rules were not met.

Keep in sync with the realm policy set by scripts/keycloak-harden.sh:

    length(12) and digits(1) and lowerCase(1) and upperCase(1)
    and notUsername(undefined) and passwordHistory(3)

`passwordHistory(3)` is deliberately absent: only Keycloak knows a user's
previous hashes, so reuse can only be caught by Keycloak itself. That path —
and any future drift between this mirror and the realm — is handled by
keycloak_admin, which parses Keycloak's own message back out of the 400.

The mirror is otherwise faithful, with one deliberate exception: `notUsername`,
which Keycloak declares but does not actually enforce on the admin API this
service uses (see the rule's comment).

There is no maximum-length rule: the realm sets none. The 128-char cap on the
request schemas is an input-size guard, not a policy rule.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

MIN_LENGTH = 12


@dataclass(frozen=True)
class Rule:
    """One password requirement.

    `clause` is a noun phrase folded into "Password must contain <a, b, and c>."
    A rule that doesn't read naturally in that list sets `clause=None` and
    supplies a standalone `sentence` instead.
    """

    id: str
    text: str  # UI checklist copy, e.g. "At least 12 characters"
    check: Callable[[str, str], bool]  # (password, username) -> satisfied?
    clause: str | None = None
    sentence: str | None = None


RULES: tuple[Rule, ...] = (
    Rule(
        id="length",
        text=f"At least {MIN_LENGTH} characters",
        check=lambda pw, _u: len(pw) >= MIN_LENGTH,
        clause=f"at least {MIN_LENGTH} characters",
    ),
    Rule(
        id="digits",
        text="At least one number",
        # isdecimal(), not isdigit(): Keycloak counts digits with Java's
        # Character.isDigit, which is category Nd. isdigit() also accepts No
        # characters like "²", so it would pass a password the realm rejects.
        check=lambda pw, _u: any(c.isdecimal() for c in pw),
        clause="at least one digit",
    ),
    Rule(
        id="lowercase",
        text="At least one lowercase letter",
        check=lambda pw, _u: any(c.islower() for c in pw),
        clause="at least one lowercase letter",
    ),
    Rule(
        id="uppercase",
        text="At least one uppercase letter",
        check=lambda pw, _u: any(c.isupper() for c in pw),
        clause="at least one uppercase letter",
    ),
    Rule(
        id="not_username",
        text="Different from your email address",
        # The realm declares notUsername, but in practice Keycloak never
        # enforces it here: it stores usernames lower-cased, so a password
        # equal to the username can't also satisfy upperCase(1) — verified
        # against Keycloak 25, which returns 201 for password == username.
        # We enforce it ourselves (case-insensitively) so the realm's declared
        # intent actually holds. This is the one rule where we are deliberately
        # stricter than Keycloak; the cost is rejecting an email-as-password,
        # which is not a password worth defending.
        # Equality only, never containment — a passphrase that merely contains
        # the address is fine.
        check=lambda pw, u: not u or pw.strip().lower() != u.strip().lower(),
        clause=None,
        sentence="Password must not be the same as your email address.",
    ),
)


def unmet_requirements(password: str, *, username: str = "") -> list[Rule]:
    """Return the rules `password` does not satisfy, in declaration order."""
    return [r for r in RULES if not r.check(password, username)]


def explain_failures(rules: Sequence[Rule]) -> str:
    """Render unmet rules as user-facing copy naming every failure."""
    sentences: list[str] = []
    clauses = [r.clause for r in rules if r.clause]
    if clauses:
        sentences.append(f"Password must contain {_join(clauses)}.")
    sentences.extend(r.sentence for r in rules if r.sentence)
    return " ".join(sentences)


def validate(password: str, *, username: str = "") -> None:
    """Raise ValueError naming every unmet requirement. No-op if compliant."""
    unmet = unmet_requirements(password, username=username)
    if unmet:
        raise ValueError(explain_failures(unmet))


def _join(parts: list[str]) -> str:
    """Oxford-comma join: 'a', 'a and b', 'a, b, and c'."""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"
