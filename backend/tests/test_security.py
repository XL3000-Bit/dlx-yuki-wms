import pytest
import jwt
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password

def test_password_is_hashed_and_verifiable() -> None:
    raw = "StrongWarehousePassword!"
    hashed = hash_password(raw)
    assert raw not in hashed
    assert verify_password(raw, hashed)
    assert not verify_password("wrong-password", hashed)

def test_access_and_refresh_tokens_are_separated() -> None:
    access = create_access_token("42"); refresh = create_refresh_token("42")
    assert decode_token(access, "access")["sub"] == "42"
    assert decode_token(refresh, "refresh")["sub"] == "42"
    with pytest.raises(jwt.InvalidTokenError): decode_token(refresh, "access")

def test_each_issued_token_is_unique() -> None:
    first = create_refresh_token("42")
    second = create_refresh_token("42")
    assert first != second
    assert decode_token(first, "refresh")["jti"] != decode_token(second, "refresh")["jti"]
