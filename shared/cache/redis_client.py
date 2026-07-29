import json
from functools import lru_cache
from typing import Any
import redis.asyncio as redis

from shared.config.settings import settings

CACHE_PREFIX="cache:"
SESSION_PREFIX="session:"
RATELIMIT_PREFIX="ratelimit:"

@lru_cache
def get_redis_pool() -> redis.ConnectionPool:
    return redis.ConnectionPool(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True

    )

def get_redis() -> redis.Redis:
    return redis.Redis(connection_pool=get_redis_pool())

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
