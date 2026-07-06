"""Redis-backed rate limiting for auth endpoints (security fix, wave 1 audit
remediation — CRITICAL: brute-forceable 6-digit pairing code + unthrottled
refresh endpoint).

Fixed-window counter per (bucket, client IP), backed by Redis INCR/EXPIRE.
Raises HTTP 429 once the limit is exceeded within the window.
"""
from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis

from daily.config import Settings


async def get_redis():
    """FastAPI dependency yielding a Redis connection (mirrors the pattern
    already used in daily.integrations.router._get_redis)."""
    settings = Settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        yield redis
    finally:
        await redis.aclose()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Fixed-window rate limiter, usable as a FastAPI dependency.

    Usage:
        @router.post("/thing", dependencies=[Depends(RateLimiter("thing", limit=10, window_seconds=60))])
    """

    def __init__(self, bucket: str, limit: int, window_seconds: int):
        self.bucket = bucket
        self.limit = limit
        self.window_seconds = window_seconds

    async def __call__(self, request: Request, redis: Redis = Depends(get_redis)) -> None:
        key = f"ratelimit:{self.bucket}:{client_ip(request)}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, self.window_seconds)
        if count > self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Try again later.",
            )
