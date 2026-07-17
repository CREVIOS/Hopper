import hashlib

from app.services import api_key_service


def test_generate_token_shape_and_uniqueness():
    t1 = api_key_service.generate_token()
    t2 = api_key_service.generate_token()
    assert t1.startswith(api_key_service.TOKEN_PREFIX)
    assert t1 != t2
    # 32 random bytes urlsafe-encoded = 43 chars + the "hop_" prefix.
    assert len(t1) == len(api_key_service.TOKEN_PREFIX) + 43


def test_hash_token_is_sha256_hex():
    token = "hop_example"
    assert api_key_service.hash_token(token) == hashlib.sha256(token.encode()).hexdigest()
    # Deterministic: the DB lookup depends on it.
    assert api_key_service.hash_token(token) == api_key_service.hash_token(token)


def test_looks_like_api_key():
    assert api_key_service.looks_like_api_key("hop_abc123")
    assert not api_key_service.looks_like_api_key("eyJhbGciOi...")  # a JWT
    assert not api_key_service.looks_like_api_key("")


def test_prefix_is_displayable_slice_of_token():
    token = api_key_service.generate_token()
    prefix = token[: api_key_service.PREFIX_LEN]
    assert token.startswith(prefix)
    assert len(prefix) < len(token)  # never the whole secret
