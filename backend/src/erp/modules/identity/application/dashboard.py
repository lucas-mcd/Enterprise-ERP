from dataclasses import dataclass
from typing import Protocol
from erp.shared.domain.security import Principal


@dataclass(frozen=True)
class ActivityItem:
    code: str
    category: str
    description: str
    status: str
    amount: str


@dataclass(frozen=True)
class AuditItem:
    id: str
    table: str
    operation: str
    occurred_at: str


@dataclass(frozen=True)
class DashboardSnapshot:
    tenant_name: str
    total_records: int
    completed: int
    total_amount: str
    activities: list[ActivityItem]
    audit: list[AuditItem]
    is_simulated: bool = True


class DashboardReader(Protocol):
    async def read(self, principal: Principal) -> DashboardSnapshot: ...


class GetDashboard:
    def __init__(self, reader: DashboardReader) -> None:
        self.reader = reader

    async def execute(self, principal: Principal) -> DashboardSnapshot:
        return await self.reader.read(principal)
