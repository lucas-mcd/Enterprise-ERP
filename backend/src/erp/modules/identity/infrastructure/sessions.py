import hashlib
import secrets
import re
from collections.abc import Awaitable
from typing import cast
import hmac
from uuid import UUID
from redis.asyncio import Redis

# All attempts count. Lua guarantees an expiry is attached atomically.
RATE_SCRIPT = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return {n, redis.call('TTL', KEYS[1])}
"""


class RateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(1, retry_after)


class RedisSessions:
    def __init__(self, redis: Redis, key_secret: str) -> None:
        self.redis = redis
        self.key_secret = key_secret

    @staticmethod
    def key(tenant: UUID, sid: UUID) -> str:
        return f"session:{tenant}:{sid}"

    async def create(self, tenant: UUID, sid: UUID, user: UUID, ttl: int) -> None:
        created = await self.redis.set(
            self.key(tenant, sid), str(user), ex=ttl, nx=True
        )
        if not created:
            raise RuntimeError("Session collision")

    async def revoke(self, tenant: UUID, sid: UUID) -> None:
        await self.redis.delete(self.key(tenant, sid), f"refresh:{tenant}:{sid}")

    async def limit(self, subject: str, maximum: int, window: int = 300) -> None:
        digest = hmac.new(
            self.key_secret.encode(), subject.encode(), hashlib.sha256
        ).hexdigest()
        count, ttl = await cast(
            Awaitable[list[int]],
            self.redis.eval(RATE_SCRIPT, 1, f"login-rate:{digest}", str(window)),
        )
        if int(count) > maximum:
            raise RateLimited(int(ttl))


ROTATE_SCRIPT = """
local ttl = redis.call('TTL', KEYS[1])
if ttl <= 0 then return 0 end
if redis.call('HGET', KEYS[1], 'current') ~= ARGV[1] then
  if redis.call('HEXISTS', KEYS[1], 'used:' .. ARGV[1]) == 1 then
    redis.call('DEL', KEYS[1], KEYS[2])
  end
  return 0
end
redis.call('HSET', KEYS[1], 'used:' .. ARGV[1], '1', 'current', ARGV[2])
local user = redis.call('HGET', KEYS[1], 'user')
redis.call('SET', KEYS[2], user, 'EX', math.min(ttl, tonumber(ARGV[3])))
return ttl
"""


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def parse_refresh(value: str) -> tuple[UUID, UUID, str]:
    tenant, sid, secret = value.split(".")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", secret):
        raise ValueError("Invalid token")
    return UUID(tenant), UUID(sid), secret


class RefreshSessions(RedisSessions):
    async def start(
        self, tenant: UUID, sid: UUID, user: UUID, access_ttl: int, refresh_ttl: int
    ) -> str:
        secret = secrets.token_urlsafe(32)
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.hset(
                f"refresh:{tenant}:{sid}",
                mapping={"user": str(user), "current": digest(secret)},
            )
            pipe.expire(f"refresh:{tenant}:{sid}", refresh_ttl)
            pipe.set(self.key(tenant, sid), str(user), ex=access_ttl)
            await pipe.execute()
        return f"{tenant}.{sid}.{secret}"

    async def user(self, tenant: UUID, sid: UUID) -> UUID | None:
        value = await cast(
            Awaitable[str | None], self.redis.hget(f"refresh:{tenant}:{sid}", "user")
        )
        return UUID(value) if value else None

    async def rotate(
        self, tenant: UUID, sid: UUID, secret: str, access_ttl: int
    ) -> tuple[str, int]:
        replacement = secrets.token_urlsafe(32)
        ttl = await cast(
            Awaitable[int],
            self.redis.eval(
                ROTATE_SCRIPT,
                2,
                f"refresh:{tenant}:{sid}",
                self.key(tenant, sid),
                digest(secret),
                digest(replacement),
                str(access_ttl),
            ),
        )
        if ttl <= 0:
            raise ValueError("Refresh expired or reused")
        return f"{tenant}.{sid}.{replacement}", ttl
