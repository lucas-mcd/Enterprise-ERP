from datetime import date
from decimal import Decimal
from uuid import UUID
from typing import Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from erp.modules.projects.infrastructure.models import Project, Allocation, Delivery
from erp.modules.assets.infrastructure.models import Asset
from erp.modules.assets.domain.depreciation import depreciation
from erp.modules.hcm.infrastructure.models import Employee
from erp.modules.operations.domain.orders import BusinessError
from erp.modules.organization.infrastructure.models import Tenant
from erp.modules.financeiro.domain.cash import NewEntry
from erp.modules.financeiro.infrastructure.repositories.cash import SqlCashRepository


class EnterpriseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tenant = session.info["audit_context"].tenant_id

    async def lock_tenant(self) -> None:
        await self.session.scalar(select(Tenant).with_for_update())

    async def project(self, identity: UUID, version: int | None = None) -> Project:
        row = await self.session.scalar(
            select(Project).where(Project.id == identity).with_for_update()
        )
        if row is None or row.is_simulated:
            raise BusinessError("Projeto real indisponível.")
        if version is not None and row.version != version:
            raise BusinessError("Projeto alterado. Atualize a tela.")
        return row

    async def allocate(
        self,
        identity: UUID,
        key: UUID,
        description: str,
        day: date,
        hours: Decimal,
        cost: Decimal,
    ) -> Allocation:
        await self.lock_tenant()
        project = await self.project(identity)
        old = await self.session.scalar(
            select(Allocation).where(Allocation.request_key == key)
        )
        if old:
            if (
                old.project_id,
                old.description,
                old.worked_on,
                old.hours,
                old.hourly_cost,
            ) != (identity, description, day, hours, cost):
                raise BusinessError("Chave reutilizada com outros dados.")
            return old
        if project.status != "em_execucao":
            raise BusinessError("Aponte horas somente em projetos em execução.")
        row = Allocation(
            tenant_id=self.tenant,
            project_id=identity,
            description=description,
            worked_on=day,
            hours=hours,
            hourly_cost=cost,
            request_key=key,
        )
        self.session.add(row)
        return row

    async def bill(
        self,
        identity: UUID,
        key: UUID,
        description: str,
        amount: Decimal,
        due: date,
        actor: UUID,
    ) -> Delivery:
        await self.lock_tenant()
        project = await self.project(identity)
        old = await self.session.scalar(
            select(Delivery).where(Delivery.request_key == key)
        )
        if old:
            if (old.project_id, old.description, old.amount, old.due_date) != (
                identity,
                description,
                amount,
                due,
            ):
                raise BusinessError("Chave reutilizada com outros dados.")
            return old
        if project.status == "planejamento":
            raise BusinessError("Inicie o projeto antes de faturar entregas.")
        row = Delivery(
            tenant_id=self.tenant,
            project_id=identity,
            description=description,
            amount=amount,
            due_date=due,
            request_key=key,
        )
        cash, _ = await SqlCashRepository(self.session).create(
            NewEntry(
                "Entrega: " + description,
                project.customer,
                "Serviços",
                "receita",
                "pendente",
                amount,
                due,
                None,
            ),
            actor,
            row.id,
        )
        row.cash_entry_id = cash.id
        self.session.add(row)
        return row

    async def assign(self, asset: Asset, employee_id: UUID | None) -> None:
        if employee_id:
            employee = await self.session.scalar(
                select(Employee)
                .where(
                    Employee.id == employee_id,
                    Employee.is_active.is_(True),
                    Employee.is_simulated.is_(asset.is_simulated),
                )
                .with_for_update()
            )
            if employee is None:
                raise BusinessError(
                    "Colaborador ativo da mesma empresa/origem não encontrado."
                )
        asset.employee_id = employee_id

    async def asset(self, identity: UUID) -> Asset:
        row = await self.session.scalar(
            select(Asset).where(Asset.id == identity).with_for_update()
        )
        if row is None or row.is_simulated:
            raise BusinessError("Ativo real indisponível.")
        return row

    async def project_views(self, rows: list[Project]) -> list[dict[str, Any]]:
        if not rows:
            return []
        ids = [r.id for r in rows]
        allocations = await self.session.execute(
            select(
                Allocation.project_id,
                func.sum(Allocation.hours),
                func.sum(Allocation.hours * Allocation.hourly_cost),
            )
            .where(Allocation.project_id.in_(ids))
            .group_by(Allocation.project_id)
        )
        totals = {r[0]: (r[1], r[2]) for r in allocations}
        bills = await self.session.execute(
            select(Delivery.project_id, func.sum(Delivery.amount))
            .where(Delivery.project_id.in_(ids))
            .group_by(Delivery.project_id)
        )
        billed = {r[0]: r[1] for r in bills}
        return [
            {
                "id": r.id,
                "code": r.code,
                "name": r.name,
                "customer": r.customer,
                "budget": str(r.budget),
                "status": r.status,
                "version": r.version,
                "is_simulated": r.is_simulated,
                "hours": str(totals.get(r.id, (0, 0))[0]),
                "cost": format(Decimal(totals.get(r.id, (0, 0))[1]), ".2f"),
                "billed": str(billed.get(r.id, 0)),
            }
            for r in rows
        ]

    async def project_view(self, row: Project) -> dict[str, Any]:
        return (await self.project_views([row]))[0]

    async def asset_view(self, row: Asset, as_of: date) -> dict[str, Any]:
        employee = (
            await self.session.scalar(
                select(Employee).where(Employee.id == row.employee_id)
            )
            if row.employee_id
            else None
        )
        return {
            "id": row.id,
            "tag": row.tag,
            "name": row.name,
            "category": row.category,
            "cost": str(row.cost),
            "residual": str(row.residual),
            "life_months": row.life_months,
            "service_on": row.service_on,
            "employee_id": row.employee_id,
            "employee_name": employee.name if employee else None,
            "version": row.version,
            "is_simulated": row.is_simulated,
            "as_of": as_of,
            **depreciation(
                row.cost, row.residual, row.life_months, row.service_on, as_of
            ),
        }
