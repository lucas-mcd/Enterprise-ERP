from typing import Protocol
from uuid import UUID
from erp.modules.financeiro.domain.cash import (
    NewEntry,
    EntryView,
    EntryFilter,
    EntryPage,
    CashSummary,
    InvalidEntry,
)


class CashRepository(Protocol):
    async def create(
        self, command: NewEntry, actor: UUID, key: UUID
    ) -> tuple[EntryView, bool]: ...

    async def page(
        self, filters: EntryFilter, page: int, page_size: int
    ) -> EntryPage: ...

    async def summary(self, filters: EntryFilter) -> CashSummary: ...


class CashService:
    def __init__(self, repository: CashRepository) -> None:
        self.repository = repository

    async def create(
        self, command: NewEntry, actor: UUID, key: UUID
    ) -> tuple[EntryView, bool]:
        command.validate()
        return await self.repository.create(command, actor, key)

    async def page(self, filters: EntryFilter, page: int, page_size: int) -> EntryPage:
        filters.validate()
        if page < 1 or not 1 <= page_size <= 100:
            raise InvalidEntry("Paginação inválida.")
        return await self.repository.page(filters, page, page_size)

    async def summary(self, filters: EntryFilter) -> CashSummary:
        filters.validate()
        return await self.repository.summary(filters)
