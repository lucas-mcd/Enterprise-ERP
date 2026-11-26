from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from erp.modules.organization.infrastructure.models import DemoActivity, Tenant
from erp.modules.identity.application.dashboard import (
    ActivityItem,
    AuditItem,
    DashboardSnapshot,
)
from erp.shared.infrastructure.database.audit import AuditLog
from erp.shared.domain.security import Principal


class SqlDashboardReader:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def read(self, principal: Principal) -> DashboardSnapshot:
        categories = []
        if "financeiro:lancamento:ler" in principal.permissions:
            categories.append("financeiro")
        if "vendas:pedido:ler" in principal.permissions:
            categories.append("vendas")
        # Bounded demo collection, not the query strategy for future OLAP modules.
        activities = list(
            await self.session.scalars(
                select(DemoActivity)
                .where(DemoActivity.category.in_(categories))
                .order_by(DemoActivity.code)
                .limit(100)
            )
        )
        tenant = await self.session.scalar(select(Tenant))
        audit: list[AuditItem] = []
        if "auditoria:registro:ler" in principal.permissions:
            logs = await self.session.scalars(
                select(AuditLog)
                .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
                .limit(10)
            )
            audit = [
                AuditItem(
                    id=str(log.id),
                    table=log.table_name,
                    operation=log.operation,
                    occurred_at=log.occurred_at.isoformat(),
                )
                for log in logs
            ]
        return DashboardSnapshot(
            tenant_name=tenant.name if tenant else "",
            total_records=len(activities),
            completed=sum(a.status == "concluido" for a in activities),
            total_amount=str(sum((a.amount for a in activities), Decimal("0"))),
            activities=[
                ActivityItem(
                    code=a.code,
                    category=a.category,
                    description=a.description,
                    status=a.status,
                    amount=str(a.amount),
                )
                for a in activities
            ],
            audit=audit,
        )
