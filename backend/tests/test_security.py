"""JWT 工具单元测试（TDD RED → GREEN）。

验证 backend.core.security 的 HS256 token 签发/验证/过期/非法处理。
"""
import jwt
import pytest

from backend.core import security


def test_create_and_decode_roundtrip():
    """签发后解码可拿到 sub。"""
    tok = security.create_access_token("operator", expires_minutes=30)
    payload = security.decode_token(tok)
    assert payload["sub"] == "operator"


def test_decode_invalid_token_raises():
    """非法 token → 抛 PyJWTError。"""
    with pytest.raises(jwt.PyJWTError):
        security.decode_token("not-a-real-token")


def test_decode_expired_token_raises():
    """过期 token（expires_minutes=-1）→ 抛 ExpiredSignatureError。"""
    tok = security.create_access_token("operator", expires_minutes=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        security.decode_token(tok)


def test_is_valid_token():
    """is_valid_token：None/非法→False，合法→True。"""
    assert security.is_valid_token(None) is False
    assert security.is_valid_token("garbage") is False
    tok = security.create_access_token("operator")
    assert security.is_valid_token(tok) is True
