import secrets
from functools import lru_cache
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type
from anyio import CapacityLimiter, to_thread


class ArgonPasswords:
    """Bound memory-heavy work; do not block the FastAPI event loop."""

    def __init__(self) -> None:
        self.hasher = PasswordHasher(
            time_cost=3,
            memory_cost=65536,
            parallelism=1,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )
        self.dummy_hash = self.hasher.hash(secrets.token_urlsafe(32))
        self.limiter = CapacityLimiter(2)

    def _verify(self, password: str, encoded: str | None) -> bool:
        try:
            result = self.hasher.verify(encoded or self.dummy_hash, password)
            return result and encoded is not None
        except (VerificationError, InvalidHashError):
            return False

    async def verify(self, password: str, encoded: str | None) -> bool:
        return await to_thread.run_sync(
            self._verify, password, encoded, limiter=self.limiter
        )

    async def hash(self, password: str) -> str:
        return await to_thread.run_sync(
            self.hasher.hash, password, limiter=self.limiter
        )

    def needs_rehash(self, encoded: str) -> bool:
        return self.hasher.check_needs_rehash(encoded)


@lru_cache
def password_service() -> ArgonPasswords:
    return ArgonPasswords()
