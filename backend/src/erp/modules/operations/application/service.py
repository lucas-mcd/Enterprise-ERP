from decimal import Decimal
from datetime import date
from typing import Protocol
from uuid import UUID
from erp.modules.operations.domain.orders import Line, BusinessError, total


class WorkflowPort(Protocol):
    async def create_order(
        self,
        actor: UUID,
        key: UUID,
        kind: str,
        counterparty: str,
        ordered_on: date,
        due_date: date,
        lines: list[Line],
        variable_cost: Decimal = Decimal("0"),
        customer_id: UUID | None = None,
    ) -> object: ...
    async def complete(self, order_id: UUID, kind: str, actor: UUID) -> object: ...


class OrderService:
    def __init__(self, repository: WorkflowPort) -> None:
        self.repository = repository

    async def create(
        self,
        actor: UUID,
        key: UUID,
        kind: str,
        counterparty: str,
        ordered_on: date,
        due_date: date,
        lines: list[Line],
        variable_cost: Decimal = Decimal("0"),
        customer_id: UUID | None = None,
    ) -> object:
        if not variable_cost.is_finite() or not 0 <= variable_cost <= Decimal(
            "999999999.99"
        ):
            raise BusinessError("Custo variável inválido.")
        total(lines)
        if (
            kind not in ("sale", "purchase")
            or not 2 <= len(counterparty.strip()) <= 120
        ):
            raise BusinessError("Pedido inválido.")
        if not date(2000, 1, 1) <= ordered_on <= due_date <= date(2100, 12, 31):
            raise BusinessError(
                "Vencimento deve ser posterior ou igual à data do pedido."
            )
        return await self.repository.create_order(
            actor,
            key,
            kind,
            counterparty,
            ordered_on,
            due_date,
            lines,
            variable_cost,
            customer_id,
        )

    async def complete(self, order_id: UUID, kind: str, actor: UUID) -> object:
        return await self.repository.complete(order_id, kind, actor)
