import hashlib
import json
from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal
from uuid import UUID
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from erp.modules.financeiro.domain.cash import (
    NewEntry,
    InvalidEntry,
    EntryView,
    EntryFilter,
    EntryPage,
    CashPoint,
    CashSummary,
    CategoryTotal,
    IdempotencyConflict,
)
from erp.modules.financeiro.infrastructure.models import CashEntry
from erp.shared.infrastructure.database.session import context


def money(value: Decimal | int | None) -> str:
    return format(Decimal(value or 0).quantize(Decimal("0.01")), ".2f")


def view(row: CashEntry) -> EntryView:
    return EntryView(
        row.id,
        row.description,
        row.counterparty,
        row.category,
        row.kind,
        row.status,
        money(row.amount),
        row.currency,
        row.due_date,
        row.settled_on,
        row.effective_on,
        row.is_simulated,
        row.version,
        row.cost_center_id,
    )


class SqlCashRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def conditions(self, filters: EntryFilter) -> list[ColumnElement[bool]]:
        conditions = [
            CashEntry.is_simulated.is_(filters.source == "demo"),
            CashEntry.effective_on >= filters.start,
            CashEntry.effective_on <= filters.end,
        ]
        if filters.status:
            conditions.append(CashEntry.status == filters.status)
        if filters.kind:
            conditions.append(CashEntry.kind == filters.kind)
        if filters.category:
            conditions.append(CashEntry.category == filters.category)
        if filters.query:
            conditions.append(
                or_(
                    CashEntry.description.icontains(filters.query, autoescape=True),
                    CashEntry.counterparty.icontains(filters.query, autoescape=True),
                )
            )
        return conditions

    async def create(
        self, command: NewEntry, actor: UUID, key: UUID
    ) -> tuple[EntryView, bool]:
        payload = asdict(command)
        if command.cost_center_id is None:
            payload.pop("cost_center_id")
        else:
            from erp.modules.integration.infrastructure.models import CostCenter

            if (
                await self.session.scalar(
                    select(CostCenter).where(CostCenter.id == command.cost_center_id)
                )
                is None
            ):
                raise InvalidEntry("Centro de custo não encontrado.")
        fingerprint = hashlib.sha256(
            json.dumps(
                payload, default=str, sort_keys=True, ensure_ascii=False
            ).encode()
        ).hexdigest()
        query = select(CashEntry).where(
            CashEntry.created_by == actor, CashEntry.request_key == key
        )
        existing = await self.session.scalar(query)
        if existing is not None:
            if existing.payload_hash != fingerprint:
                raise IdempotencyConflict()
            return view(existing), False
        row = CashEntry(
            cost_center_id=command.cost_center_id,
            tenant_id=context(self.session.sync_session).tenant_id,
            description=command.description,
            counterparty=command.counterparty,
            category=command.category,
            kind=command.kind,
            status=(
                "aguardando_aprovacao"
                if command.amount > Decimal("5000")
                else command.status
            ),
            amount=command.amount,
            currency="BRL",
            due_date=command.due_date,
            settled_on=None if command.amount > Decimal("5000") else command.settled_on,
            effective_on=(
                command.due_date
                if command.amount > Decimal("5000")
                else command.settled_on or command.due_date
            ),
            is_simulated=False,
            created_by=actor,
            request_key=key,
            payload_hash=fingerprint,
        )
        try:
            # A duplicate key race rolls back both row and audit within this savepoint.
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
        except IntegrityError:
            existing = await self.session.scalar(query)
            if existing is None:
                raise
            if existing.payload_hash != fingerprint:
                raise IdempotencyConflict() from None
            return view(existing), False
        return view(row), True

    async def page(self, filters: EntryFilter, page: int, page_size: int) -> EntryPage:
        conditions = self.conditions(filters)
        total = await self.session.scalar(
            select(func.count()).select_from(CashEntry).where(*conditions)
        )
        rows = await self.session.scalars(
            select(CashEntry)
            .where(*conditions)
            .order_by(
                (
                    getattr(CashEntry, filters.sort).desc()
                    if filters.desc
                    else getattr(CashEntry, filters.sort).asc()
                ),
                CashEntry.created_at.desc(),
                CashEntry.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return EntryPage([view(row) for row in rows], total or 0, page, page_size)

    async def summary(self, filters: EntryFilter) -> CashSummary:
        sums = [
            func.sum(
                case(
                    (
                        (CashEntry.kind == kind)
                        & (
                            CashEntry.status.in_(["pendente", "aguardando_aprovacao"])
                            if status == "pendente"
                            else CashEntry.status == status
                        ),
                        CashEntry.amount,
                    ),
                    else_=Decimal("0"),
                )
            )
            for kind, status in [
                ("receita", "concluido"),
                ("despesa", "concluido"),
                ("receita", "pendente"),
                ("despesa", "pendente"),
            ]
        ]
        rows = await self.session.execute(
            select(CashEntry.effective_on, *sums, func.count())
            .where(*self.conditions(filters))
            .group_by(CashEntry.effective_on)
        )
        grouped = {row[0]: row for row in rows}
        totals = [Decimal("0") for _ in range(4)]
        count = 0
        points = []
        day = filters.start
        while day <= filters.end:
            row = grouped.get(day)
            values = [
                Decimal(row[i + 1] or 0) if row else Decimal("0") for i in range(4)
            ]
            totals = [total + value for total, value in zip(totals, values)]
            count += int(row[5]) if row else 0
            points.append(CashPoint(day, *(money(value) for value in values)))
            day += timedelta(days=1)
        categories = await self.session.execute(
            select(CashEntry.category, func.sum(CashEntry.amount))
            .where(*self.conditions(filters), CashEntry.kind == "despesa")
            .group_by(CashEntry.category)
            .order_by(func.sum(CashEntry.amount).desc(), CashEntry.category)
        )
        return CashSummary(
            filters.source,
            count,
            money(totals[0]),
            money(totals[1]),
            money(totals[0] - totals[1]),
            money(totals[2]),
            money(totals[3]),
            points,
            [CategoryTotal(row[0], money(row[1])) for row in categories],
        )
