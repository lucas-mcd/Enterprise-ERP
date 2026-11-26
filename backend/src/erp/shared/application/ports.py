from types import TracebackType
from typing import Protocol, Self
from uuid import UUID
from erp.shared.domain.security import Principal


class IdentityReader(Protocol):
    async def principal(self, user_id: UUID) -> Principal | None: ...


class UnitOfWork(Protocol):
    identities: IdentityReader

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...
