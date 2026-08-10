"""
Run from the project root:
    pytest shared/tests/test_redis_pubsub.py -q
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.cache.redis_client import (
    DOCUMENT_STATUS_CHANNEL_PREFIX,
    publish_document_status,
    subscribe_document_status,
)


def test_publish_document_status_publishes_to_the_owner_scoped_channel():
    fake_client = MagicMock()
    with patch("shared.cache.redis_client.redis_sync.Redis", return_value=fake_client):
        publish_document_status("owner-123", {"status": "processed"})

    fake_client.publish.assert_called_once_with(
        f"{DOCUMENT_STATUS_CHANNEL_PREFIX}owner-123", json.dumps({"status": "processed"})
    )
    fake_client.close.assert_called_once()


def test_publish_document_status_closes_the_connection_even_if_publish_raises():
    fake_client = MagicMock()
    fake_client.publish.side_effect = RuntimeError("redis unreachable")
    with patch("shared.cache.redis_client.redis_sync.Redis", return_value=fake_client):
        with pytest.raises(RuntimeError):
            publish_document_status("owner-123", {"status": "processed"})

    fake_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_subscribe_document_status_yields_decoded_payloads_and_skips_non_message_events():
    fake_pubsub = MagicMock()

    async def fake_listen():
        yield {"type": "subscribe", "data": 1}  # the subscription-confirmation event
        yield {"type": "message", "data": json.dumps({"status": "processed"})}
        yield {"type": "message", "data": json.dumps({"status": "failed"})}

    fake_pubsub.subscribe = AsyncMock()
    fake_pubsub.unsubscribe = AsyncMock()
    fake_pubsub.aclose = AsyncMock()
    fake_pubsub.listen = fake_listen

    fake_client = MagicMock()
    fake_client.pubsub.return_value = fake_pubsub

    with patch("shared.cache.redis_client.get_redis", return_value=fake_client):
        received = []
        async for message in subscribe_document_status("owner-123"):
            received.append(message)

    assert received == [{"status": "processed"}, {"status": "failed"}]
    fake_pubsub.subscribe.assert_awaited_once_with(f"{DOCUMENT_STATUS_CHANNEL_PREFIX}owner-123")
    fake_pubsub.unsubscribe.assert_awaited_once_with(f"{DOCUMENT_STATUS_CHANNEL_PREFIX}owner-123")
    fake_pubsub.aclose.assert_awaited_once()
