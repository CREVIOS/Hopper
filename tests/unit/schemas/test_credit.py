from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.credit import CreditBalanceResponse, CreditHistoryResponse


def test_credit_balance_response_accepts_numeric_balance():
    response = CreditBalanceResponse(account_id="acct-1", balance=12.5)

    assert response.account_id == "acct-1"
    assert response.balance == 12.5


def test_credit_balance_response_coerces_integer_balance_to_float():
    response = CreditBalanceResponse(account_id="acct-1", balance=10)

    assert response.balance == 10.0


def test_credit_history_response_defaults_pod_id_to_none():
    response = CreditHistoryResponse(
        id="entry-1",
        account_id="acct-1",
        amount=2.5,
        direction="debit",
        type="pod_usage",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
    )

    assert response.pod_id is None


def test_credit_history_response_parses_datetime_and_serializes():
    response = CreditHistoryResponse(
        id="entry-1",
        account_id="acct-1",
        amount=2.5,
        direction="credit",
        type="allocation",
        pod_id="pod-1",
        created_at="2026-01-01T12:00:00",
    )

    assert response.created_at == datetime(2026, 1, 1, 12, 0, 0)
    assert response.model_dump() == {
        "id": "entry-1",
        "account_id": "acct-1",
        "amount": 2.5,
        "direction": "credit",
        "type": "allocation",
        "pod_id": "pod-1",
        "created_at": datetime(2026, 1, 1, 12, 0, 0),
    }


def test_credit_history_response_supports_from_attributes():
    class EntryRow:
        id = "entry-1"
        account_id = "acct-1"
        amount = 4
        direction = "debit"
        type = "pod_usage"
        pod_id = None
        created_at = datetime(2026, 1, 1, 12, 0, 0)

    response = CreditHistoryResponse.model_validate(EntryRow(), from_attributes=True)

    assert response.amount == 4.0
    assert response.direction == "debit"


def test_credit_history_response_requires_created_at():
    with pytest.raises(ValidationError) as exc_info:
        CreditHistoryResponse(
            id="entry-1",
            account_id="acct-1",
            amount=2.5,
            direction="debit",
            type="pod_usage",
        )

    assert "created_at" in str(exc_info.value)
