import pytest

from app.routers.ssh_keys import _compute_fingerprint


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
