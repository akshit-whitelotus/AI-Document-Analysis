"""
Run from document-service/:
    pytest tests/unit/test_ws_manager.py -q
"""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.ws_manager import DocumentStatusConnectionManager


def make_fake_websocket():
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


def test_connect_then_disconnect_removes_the_connection():
    manager = DocumentStatusConnectionManager()
    owner_id = uuid4()
    ws = make_fake_websocket()

    manager.connect(owner_id, ws)
    assert manager.connection_count(owner_id) == 1

    manager.disconnect(owner_id, ws)
    assert manager.connection_count(owner_id) == 0


def test_a_user_can_have_multiple_connections_eg_multiple_tabs():
    manager = DocumentStatusConnectionManager()
    owner_id = uuid4()
    ws1, ws2 = make_fake_websocket(), make_fake_websocket()

    manager.connect(owner_id, ws1)
    manager.connect(owner_id, ws2)

    assert manager.connection_count(owner_id) == 2


@pytest.mark.asyncio
async def test_send_to_owner_reaches_all_of_that_owners_connections():
    manager = DocumentStatusConnectionManager()
    owner_id = uuid4()
    ws1, ws2 = make_fake_websocket(), make_fake_websocket()
    manager.connect(owner_id, ws1)
    manager.connect(owner_id, ws2)

    await manager.send_to_owner(owner_id, {"status": "processed"})

    ws1.send_json.assert_awaited_once_with({"status": "processed"})
    ws2.send_json.assert_awaited_once_with({"status": "processed"})


@pytest.mark.asyncio
async def test_send_to_owner_never_reaches_a_different_owners_connections():
    manager = DocumentStatusConnectionManager()
    owner_a, owner_b = uuid4(), uuid4()
    ws_a, ws_b = make_fake_websocket(), make_fake_websocket()
    manager.connect(owner_a, ws_a)
    manager.connect(owner_b, ws_b)

    await manager.send_to_owner(owner_a, {"status": "processed"})

    ws_a.send_json.assert_awaited_once()
    ws_b.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_to_owner_with_no_connections_is_a_safe_noop():
    manager = DocumentStatusConnectionManager()
    await manager.send_to_owner(uuid4(), {"status": "processed"})  # must not raise


@pytest.mark.asyncio
async def test_a_send_failure_on_one_connection_disconnects_only_that_one_and_others_still_get_it():
    manager = DocumentStatusConnectionManager()
    owner_id = uuid4()
    dead_ws = make_fake_websocket()
    dead_ws.send_json.side_effect = RuntimeError("connection closed")
    alive_ws = make_fake_websocket()
    manager.connect(owner_id, dead_ws)
    manager.connect(owner_id, alive_ws)

    await manager.send_to_owner(owner_id, {"status": "processed"})

    assert manager.connection_count(owner_id) == 1
    alive_ws.send_json.assert_awaited_once()


def test_disconnect_of_an_unknown_connection_is_a_safe_noop():
    manager = DocumentStatusConnectionManager()
    manager.disconnect(uuid4(), make_fake_websocket())  # must not raise
