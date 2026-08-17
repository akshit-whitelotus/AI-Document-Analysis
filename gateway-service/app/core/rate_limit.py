import hashlib


from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from shared.cache.redis_client import RateLimiter
from shared.config.settings import settings

_limiter=RateLimiter(limit=settings.RATE_LIMIT_PER_MINUTE,window_seconds=60)

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request:Request, call_next):
        identity=request.client.host if request.client else "unknown"
        auth_header=request.headers.get("authorization")
        if auth_header:
            # Hashed rather than used raw - the raw value is a bearer JWT,
            # and using it verbatim would put live access/refresh tokens in
            # plaintext into Redis key names (visible via KEYS/MONITOR, RDB 
            # snapshots, or any tool that inspect Redis). A SHA-256 digest
            # still uniquely identifies "this token" for rate-limiting
            # purposes without exposing the token itself anywhere.
            identity=hashlib.sha256(auth_header.encode()).hexdigest()
        allowed,remaining=await _limiter.is_allowed(identity)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"error":"RateLimitExceeded","message":"Too many requests,slow down."}
            )
        response=await call_next(request)
        response.headers["X-Ratelimit-Remaining"]=str(remaining)
        return response
    