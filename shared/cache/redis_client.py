import json
from functools import lru_cache
from typing import Any, AsyncIterator
import redis as redis_sync
import redis.asyncio as redis

from shared.config.settings import settings

CACHE_PREFIX="cache:"
SESSION_PREFIX="session:"
RATELIMIT_PREFIX="ratelimit:"
DOCUMENT_STATUS_CHANNEL_PREFIX="document_status:"
TOKEN_BLACKLIST_PREFIX="token_blacklist:"

@lru_cache
def get_redis_pool() -> redis.ConnectionPool:
    return redis.ConnectionPool(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None,
        decode_responses=True

    )

def get_redis() -> redis.Redis:
    return redis.Redis(connection_pool=get_redis_pool())

def publish_document_status(owner_id:str,payload:dict) -> None:
    """
    SYNC publish - deliberately uses the plain (non-asyncio) redis client,
    because this is called from ai-worker-service's Celery task functions,
    which are plain `def`, not `async def` (Celery's sync worker model, see
    app/db/session.py using a sync SQLAlchemy session for the same reason).

    Fire-and-forget: if no one is subscribed (e.g. the user has no
    WebSocket connection open right now), the message is simply dropped -
    Redis pub/sub has no durability or replay. That's fine here because
    the document's real status is already persisted in Postgres; this
    channel only exists so the frontend doesn't have to poll for it, not
    as the source of truth.
    """
    client=redis_sync.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None,
        decode_responses=True,
    )
    try:
        client.publish(f"{DOCUMENT_STATUS_CHANNEL_PREFIX}{owner_id}",json.dumps(payload))
    finally:
        client.close()

async def subscribe_document_status(owner_id:str) -> AsyncIterator[dict]:
    """
    Async generator yielding decoded payloads published to this owner's
    document-status channel. Used by document-service's WebSocket route -
    one subscription per open WebSocket connection.
    """
    client=get_redis()
    pubsub=client.pubsub()
    channel=f"{DOCUMENT_STATUS_CHANNEL_PREFIX}{owner_id}"
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            yield json.loads(message["data"])
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()

class CacheClient:
    def __init__(self,prefix:str=CACHE_PREFIX):
        self._prefix=prefix
        self._redis=get_redis()
    def _key(self,key:str) -> str :
        return f"{self._prefix}{key}"

    async def get(self,key:str) -> Any | None :
        raw=await self._redis.get(self._key(key))
        return json.loads(raw) if raw is not None else None

    async def set(self,key:str,value:Any,ttl_seconds:int = 300) -> None:
        await self._redis.set(self._key(key),json.dumps(value),ex=ttl_seconds)
    async def delete(self,key:str) -> None:
        await self._redis.delete(self._key(key))

class SessionStore(CacheClient):
    def __init__(self):
        super().__init__(prefix=SESSION_PREFIX)

class TokenBlacklist(CacheClient):
    """
    Marks individual tokens (by their `jti` claim - see shared.security.jwt)
    as revoked, e.g. on logout or when a refresh token is rotated. Each
    entry's TTL matches the token's own remaining lifetime (see
    shared.security.jwt.remaining_ttl_seconds), so Redis auto-cleans up
    entries for tokens that would have expired naturally anyway - nothing
    accumulates forever.
    """
    def __init__(self):
        super().__init__(prefix=TOKEN_BLACKLIST_PREFIX)

    async def revoke(self,jti:str,ttl_seconds:int) -> None:
        if ttl_seconds <= 0:
            return  # already expired on its own; nothing to blacklist
        await self.set(jti,True,ttl_seconds=ttl_seconds)

    async def is_revoked(self,jti:str) -> bool:
        return await self.get(jti) is not None

class RateLimiter:
    def __init__(self,limit:int,window_seconds:int):
        self.limit=limit
        self.window_seconds=window_seconds
        self._redis=get_redis()
    async def is_allowed(self,identity:str) -> tuple[bool,int]:
        key=f"{RATELIMIT_PREFIX}{identity}"
        current=await self._redis.incr(key)
        if current == 1 :
            await self._redis.expire(key,self.window_seconds)
        remaining=max(self.limit-current,0)
        return current <=self.limit,remaining   