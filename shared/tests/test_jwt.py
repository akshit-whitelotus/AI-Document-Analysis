import time
from uuid import uuid4
import pytest
from shared.security.jwt import create_access_token,create_refresh_token,decode_token
from shared.exceptions.exceptions import UnauthorizedException

def test_access_token_round_trips_subject_and_claims():
    user_id = uuid4()
    token = create_access_token(user_id,extra_claims={"email":"a@b.com","role":"user"})
    payload = decode_token(token,expected_type="access")

    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"
    assert payload["email"] == "a@b.com"
    assert payload["role"] == "user"

def test_refresh_token_has_refresh_type():
    user_id = uuid4()
    token= create_refresh_token(user_id)
    payload = decode_token(token,expected_type="refresh")

    assert payload["type"] == "refresh"

def test_decode_rejects_wrong_token_type():
    user_id = uuid4()
    access_token=create_access_token(user_id)

    with pytest.raises(UnauthorizedException):
        decode_token(access_token,expected_type="refresh")

def test_decode_rejects_wrong_token_type():
    user_id=uuid4()
    access_token = create_access_token(user_id)

    with pytest.raises(UnauthorizedException):
        decode_token(access_token,expected_type="refresh")

def test_decode_rejects_garbage_token():
    with pytest.raises(UnauthorizedException):
        decode_token("not-a-real-token",expected_type="access")

def test_decodes_rejects_tampered_token():
    user_id = uuid4()
    token=create_access_token(user_id)
    tampered =token[:-4] + ("aaaa" if token[-4:] != "aaaa" else "bbbb")

    with pytest.raises(UnauthorizedException):
        decode_token(tampered,expected_type="access")