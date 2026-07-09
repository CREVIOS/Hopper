import pytest
from fastapi import HTTPException

from app.models.ssh_key import SSHKey
from app.routers.ssh_keys import _compute_fingerprint, AddKeyRequest, add_key, delete_key, list_keys
from app.schemas.user import TokenPayload


def test_compute_fingerprint_returns_sha256_fingerprint():
    public_key = (
        "ssh-rsa "
        "AAAAB3NzaC1yc2EAAAADAQABAAABAQC7QJt2hM8l8sM4YqzQ2+6L4Y8r7v3rQxw9fV1a8K"
    )

    fingerprint = _compute_fingerprint(public_key)

    assert fingerprint.startswith("SHA256:")


def test_compute_fingerprint_rejects_invalid_public_key():
    with pytest.raises(ValueError) as exc_info:
        _compute_fingerprint("not-a-real-key")

    assert "Invalid SSH public key format" in str(exc_info.value)


def _payload() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        email="user@example.com",
        name="Test User",
        role="student",
        exp=1234567890,
    )


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        if isinstance(self._rows, list):
            return self._rows[0] if self._rows else None
        return self._rows


class FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalarResult(self._rows)

    def scalar_one_or_none(self):
        if isinstance(self._rows, list):
            return self._rows[0] if self._rows else None
        return self._rows


class FakeDB:
    def __init__(self, execute_results=None, scalar_results=None):
        self.execute_results = list(execute_results or [])
        self.scalar_results = list(scalar_results or [])
        self.added = []
        self.committed = False
        self.deleted = None

    async def execute(self, stmt, params=None):
        return FakeExecuteResult(self.execute_results.pop(0))

    async def scalar(self, stmt):
        return self.scalar_results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def delete(self, obj):
        self.deleted = obj


async def test_list_keys_formats_public_key_preview():
    key = SSHKey(
        id="key-1",
        user_id="user-1",
        name="Laptop",
        public_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
        fingerprint="SHA256:abc",
    )
    db = FakeDB(execute_results=[[key]])

    result = await list_keys(current_user=_payload(), db=db)

    assert result[0]["id"] == "key-1"
    assert result[0]["public_key"].endswith("...")


async def test_add_key_rejects_invalid_prefix():
    with pytest.raises(HTTPException) as exc_info:
        await add_key(
            AddKeyRequest(name="Laptop", public_key="invalid-key"),
            current_user=_payload(),
            db=FakeDB(),
        )

    assert exc_info.value.status_code == 400


async def test_add_key_rejects_duplicate_fingerprint(monkeypatch):
    monkeypatch.setattr("app.routers.ssh_keys._compute_fingerprint", lambda key: "SHA256:abc")
    db = FakeDB(scalar_results=[object()])

    with pytest.raises(HTTPException) as exc_info:
        await add_key(
            AddKeyRequest(name="Laptop", public_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIabc"),
            current_user=_payload(),
            db=db,
        )

    assert exc_info.value.status_code == 409


async def test_add_key_rejects_when_key_limit_reached(monkeypatch):
    monkeypatch.setattr("app.routers.ssh_keys._compute_fingerprint", lambda key: "SHA256:abc")
    db = FakeDB(scalar_results=[None, 10])

    with pytest.raises(HTTPException) as exc_info:
        await add_key(
            AddKeyRequest(name="Laptop", public_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIabc"),
            current_user=_payload(),
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Maximum 10 SSH keys allowed"


async def test_add_key_creates_key_record(monkeypatch):
    monkeypatch.setattr("app.routers.ssh_keys._compute_fingerprint", lambda key: "SHA256:abc")
    db = FakeDB(scalar_results=[None, 0])

    result = await add_key(
        AddKeyRequest(name="Laptop", public_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIabc"),
        current_user=_payload(),
        db=db,
    )

    assert result["fingerprint"] == "SHA256:abc"
    assert db.committed is True
    assert db.added[0].name == "Laptop"


async def test_delete_key_rejects_missing_key():
    db = FakeDB(execute_results=[None])

    with pytest.raises(HTTPException) as exc_info:
        await delete_key("missing", current_user=_payload(), db=db)

    assert exc_info.value.status_code == 404


async def test_delete_key_deletes_existing_key():
    key = SSHKey(
        id="key-1",
        user_id="user-1",
        name="Laptop",
        public_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIabc",
        fingerprint="SHA256:abc",
    )
    db = FakeDB(execute_results=[key])

    result = await delete_key("key-1", current_user=_payload(), db=db)

    assert result == {"message": "deleted"}
    assert db.deleted is key
    assert db.committed is True
