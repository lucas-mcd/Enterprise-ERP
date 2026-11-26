from dataclasses import asdict
from decimal import Decimal
from datetime import date
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from erp.modules.financeiro.domain.cash import EntryFilter
from erp.modules.financeiro.infrastructure.models import CashEntry
from erp.modules.financeiro.infrastructure.repositories.cash import (
    SqlCashRepository,
    view,
)
from erp.modules.operations.domain.orders import BusinessError
from erp.shared.infrastructure.database.audit import AuditLog

MAX_ROWS = 5000


def selection(data: dict[str, Any]) -> EntryFilter:
    result = EntryFilter(
        date.fromisoformat(data["start"]),
        date.fromisoformat(data["end"]),
        data["source"],
        data.get("status"),
        data.get("kind"),
        data.get("query", ""),
        data.get("category"),
        data.get("sort", "effective_on"),
        data.get("desc", True),
    )
    result.validate()
    return result


async def report_data(
    session: AsyncSession, filters: EntryFilter, audit: bool = False
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    repo = SqlCashRepository(session)
    entities = list(
        await session.scalars(
            select(CashEntry)
            .where(*repo.conditions(filters))
            .order_by(
                (
                    getattr(CashEntry, filters.sort).desc()
                    if filters.desc
                    else getattr(CashEntry, filters.sort).asc()
                ),
                CashEntry.id,
            )
            .limit(MAX_ROWS + 1)
        )
    )
    if len(entities) > MAX_ROWS:
        raise BusinessError(
            "Exportação limitada a 5.000 registros. Reduza o período ou os filtros."
        )
    rows = [asdict(view(row)) for row in entities]
    totals = {
        (k, s): sum(
            (
                e.amount
                for e in entities
                if e.kind == k
                and ("pendente" if e.status == "aguardando_aprovacao" else e.status)
                == s
            ),
            Decimal("0"),
        )
        for k in ("receita", "despesa")
        for s in ("pendente", "concluido")
    }
    summary = {
        "income": str(totals["receita", "concluido"]),
        "expense": str(totals["despesa", "concluido"]),
        "net": str(totals["receita", "concluido"] - totals["despesa", "concluido"]),
        "pending_income": str(totals["receita", "pendente"]),
        "pending_expense": str(totals["despesa", "pendente"]),
    }
    logs = []
    if audit and entities:
        events = await session.scalars(
            select(AuditLog)
            .where(
                AuditLog.table_name == "cash_entries",
                AuditLog.entity_id.in_([r.id for r in entities]),
            )
            .order_by(AuditLog.occurred_at.desc())
            .limit(100)
        )
        logs = [
            {
                "occurred_at": e.occurred_at,
                "operation": e.operation,
                "entity_id": e.entity_id,
                "actor_id": e.actor_id,
            }
            for e in events
        ]
    return rows, summary, logs
