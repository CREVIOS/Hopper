"""Password policy mirror — unit tests.

The policy here must stay in lockstep with the Keycloak `hopper` realm
(scripts/keycloak-harden.sh). These tests pin the rules that the realm
enforces so a drift shows up as a test failure rather than as a 502 in
the user's face.
"""
import pytest

from app.services.password_policy import (
    MIN_LENGTH,
    describe_requirements,
    explain_failures,
    unmet_requirements,
    validate,
)

# Satisfies every rule: 12+ chars, a digit, a lower, an upper.
GOOD = "CorrectHorse9Battery"


class TestUnmetRequirements:
    def test_compliant_password_has_no_unmet_requirements(self):
        assert unmet_requirements(GOOD, username="jane@cs.du.ac.bd") == []

    def test_all_digits_password_reports_lower_and_upper(self):
        # The exact password from the bug report: 15 chars, passes the old
        # length-only check, rejected by Keycloak for missing case classes.
        unmet = unmet_requirements("111111111111111", username="jane@cs.du.ac.bd")
        assert {r.id for r in unmet} == {"lowercase", "uppercase"}

    def test_too_short_reports_length(self):
        unmet = unmet_requirements("Ab1", username="jane@cs.du.ac.bd")
        assert "length" in {r.id for r in unmet}

    def test_exactly_min_length_passes_length_rule(self):
        pw = "Abcdefghij1k"
        assert len(pw) == MIN_LENGTH
        assert "length" not in {r.id for r in unmet_requirements(pw, username="x@y.z")}

    def test_long_password_is_accepted(self):
        # The realm policy sets no upper bound — the 128-char cap is an
        # input-size guard on the request schema, not a policy rule. A long
        # passphrase must not be reported as non-compliant here.
        assert unmet_requirements("A1" + ("a" * 100), username="x@y.z") == []

    @pytest.mark.parametrize(
        "password,missing",
        [
            ("nodigitsatallhere", {"digits", "uppercase"}),
            ("NOLOWERCASE12345", {"lowercase"}),
            ("nouppercase12345", {"uppercase"}),
            ("NoDigitsButCased", {"digits"}),
        ],
    )
    def test_each_character_class_rule(self, password, missing):
        assert {r.id for r in unmet_requirements(password, username="x@y.z")} == missing

    def test_password_equal_to_username_is_rejected(self):
        # The realm declares notUsername but never fires it (Keycloak 25
        # returns 201 for password == username, because it lower-cases the
        # stored username). We enforce it here instead — deliberately stricter.
        email = "Student1@cs.du.ac.bd"
        unmet = unmet_requirements(email, username=email)
        assert "not_username" in {r.id for r in unmet}

    def test_username_comparison_is_case_insensitive(self):
        # Keycloak's own comparison is case-sensitive; ours is not, so
        # re-casing the address doesn't sneak it through as a password.
        unmet = unmet_requirements("Student1@cs.du.ac.bd", username="STUDENT1@CS.DU.AC.BD")
        assert "not_username" in {r.id for r in unmet}

    def test_password_containing_username_is_allowed(self):
        # Equality only, never containment — a passphrase built around the
        # address is a fine password and Keycloak would accept it.
        unmet = unmet_requirements("x@y.zAndMore99", username="x@y.z")
        assert "not_username" not in {r.id for r in unmet}

    def test_missing_username_does_not_crash(self):
        assert unmet_requirements(GOOD, username="") == []

    def test_superscript_two_is_not_a_digit(self):
        # Keycloak counts digits with Java's Character.isDigit (category Nd).
        # str.isdigit() would accept "²" (category No) and let through a
        # password the realm then rejects; str.isdecimal() matches Java.
        unmet = unmet_requirements("abcdefghijkA²", username="x@y.z")
        assert "digits" in {r.id for r in unmet}

    def test_non_ascii_letters_count_as_case(self):
        # Character.isUpperCase/isLowerCase are Unicode-aware, so "Ábcdefghij1"
        # satisfies both case rules. Rejecting it here would contradict the
        # realm and leave the UI checklist unsatisfiable.
        unmet = unmet_requirements("Ábcdefghij1k", username="x@y.z")
        assert unmet == []


class TestValidate:
    def test_validate_accepts_compliant_password(self):
        validate(GOOD, username="jane@cs.du.ac.bd")  # must not raise

    def test_validate_raises_with_itemised_reason(self):
        with pytest.raises(ValueError) as exc:
            validate("111111111111111", username="jane@cs.du.ac.bd")
        msg = str(exc.value)
        assert "lowercase letter" in msg
        assert "uppercase letter" in msg
        # The old blanket copy must not come back.
        assert "Try again later" not in msg


class TestExplainFailures:
    def test_message_names_every_unmet_rule(self):
        msg = explain_failures(unmet_requirements("aaaaaaaaaaaa", username="x@y.z"))
        assert "digit" in msg
        assert "uppercase letter" in msg

    def test_message_is_a_single_sentence_for_one_failure(self):
        msg = explain_failures(unmet_requirements("aaaaaaaaaaaa1", username="x@y.z"))
        assert msg.startswith("Password must contain")
        assert msg.endswith(".")
        assert " and " not in msg  # only one unmet rule -> no list

    def test_length_failure_reads_naturally(self):
        msg = explain_failures(unmet_requirements("Ab1", username="x@y.z"))
        assert f"at least {MIN_LENGTH} characters" in msg


class TestDescribeRequirements:
    def test_requirements_are_exposed_for_the_ui(self):
        ids = {r.id for r in describe_requirements()}
        assert ids == {"length", "digits", "lowercase", "uppercase", "not_username"}

    def test_every_requirement_has_human_copy(self):
        for r in describe_requirements():
            assert r.text and r.text[0].isupper()
