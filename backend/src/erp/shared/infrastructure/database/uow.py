from erp.modules.operations.infrastructure.repository import OperationsRepository
from types import TracebackType
from erp.modules.financeiro.infrastructure.repositories.cash import SqlCashRepository
from erp.modules.identity.infrastructure.repositories.dashboard import (
    SqlDashboardReader,
)
from typing import Self
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from erp.modules.identity.infrastructure.repositories.identity import SqlIdentityReader
from erp.shared.infrastructure.database.context import AuditContext


class SqlUnitOfWork:
    """One transaction per use case. Repositories never commit independently."""

    def __init__(
        self, factory: async_sessionmaker[AsyncSession], audit_context: AuditContext
    ) -> None:
        self.session = factory(info={"audit_context": audit_context})
        self.identities = SqlIdentityReader(self.session)
        self.dashboard = SqlDashboardReader(self.session)
        self.cash = SqlCashRepository(self.session)
        self.operations = OperationsRepository(self.session)

    async def __aenter__(self) -> Self:
        await self.session.begin()
        return self

    async def commit(self) -> None:
        await self.session.commit()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            await self.session.rollback()  # No-op after explicit commit.
        finally:
            await self.session.close()
