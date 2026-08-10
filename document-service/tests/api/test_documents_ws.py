"""
Run from document-service/:
    pytest tests/api/test_documents_ws.py -q
"""
from unittest.mock import patch
from uuid import uuid4

import pytest
from starlette.testclient import TestClient

from app.main import app
from shared.security.oauth import CurrentUser


async def _fake_status_stream(messages: list[dict]):
    for message in messages:
        yield message


def test_ws_rejects_connection_with_no_token():
    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/api/v1/documents/ws"):
            pass


def test_ws_rejects_connection_with_an_invalid_token():
    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/api/v1/documents/ws?token=not-a-real-token"):
            pass


def test_ws_accepts_a_valid_token_and_forwards_status_updates():
    user_id = uuid4()
    with patch(
        "app.api.v1.documents_ws.resolve_user_from_token",
        return_value=CurrentUser(id=user_id, raw_claims={}),
    ), patch(
        "app.api.v1.documents_ws.subscribe_document_status",
        return_value=_fake_status_stream([
            {"document_id": "doc-1", "status": "processed", "chunk_count": 3},
        ]),
    ):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/documents/ws?token=valid-token") as websocket:
            message = websocket.receive_json()

    assert message == {"document_id": "doc-1", "status": "processed", "chunk_count": 3}


def test_ws_forwards_multiple_status_updates_in_order():
    user_id = uuid4()
    messages = [
        {"document_id": "doc-1", "status": "processing"},
        {"document_id": "doc-1", "status": "processed", "chunk_count": 2},
    ]
    with patch(
        "app.api.v1.documents_ws.resolve_user_from_token",
        return_value=CurrentUser(id=user_id, raw_claims={}),
    ), patch(
        "app.api.v1.documents_ws.subscribe_document_status",
        return_value=_fake_status_stream(messages),
    ):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/documents/ws?token=valid-token") as websocket:
            received = [websocket.receive_json(), websocket.receive_json()]

    assert received == messages


def test_ws_disconnects_are_cleaned_up_from_the_connection_manager():
    import time
    from app.core.ws_manager import manager

    user_id = uuid4()
    with patch(
        "app.api.v1.documents_ws.resolve_user_from_token",
        return_value=CurrentUser(id=user_id, raw_claims={}),
    ), patch(
        "app.api.v1.documents_ws.subscribe_document_status",
        return_value=_fake_status_stream([]),  # never sends anything
    ):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/documents/ws?token=valid-token"):
            assert manager.connection_count(user_id) == 1

    # The route's manager.disconnect() call runs inside a server-side
    # asyncio task triggered by the disconnect - it can genuinely still be
    # finishing at the exact instant TestClient's context manager exits, so
    # poll briefly rather than asserting immediately (avoids a rare timing
    # flake without weakening what's actually being verified).
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and manager.connection_count(user_id) != 0:
        time.sleep(0.02)
    assert manager.connection_count(user_id) == 0
