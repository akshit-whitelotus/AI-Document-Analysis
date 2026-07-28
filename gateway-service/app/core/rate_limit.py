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
            identity=auth_header
        allowed,remaining=await _limiter.is_allowed(identity)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"error":"RateLimitExceeded","message":"Too many requests,slow down."}
            )
        response=await call_next(request)
        response.headers["X-Ratelimit-Remaining"]=str(remaining)
        return response
    