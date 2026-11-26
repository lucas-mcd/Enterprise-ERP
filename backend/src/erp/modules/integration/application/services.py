import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.sql.elements import ColumnElement
from erp.modules.integration.infrastructure.models import (
    Customer,
    Opportunity,
    BankBatch,
    BankTransaction,
)
from erp.modules.financeiro.infrastructure.models import CashEntry
from erp.modules.financeiro.domain.cash import business_today
from erp.modules.identity.infrastructure.models import User
from erp.modules.operations.infrastructure.models import Order, Product
from erp.modules.operations.application.service import OrderService
from erp.modules.operations.domain.orders import BusinessError, Line, total
from erp.shared.infrastructure.database.uow import SqlUnitOfWork
from erp.shared.infrastructure.database.base import utcnow


def fingerprint(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, default=str, sort_keys=True).encode()
    ).hexdigest()


class IntegrationService:
    """Transactional orchestration; only the presentation layer commits the UoW."""

    def __init__(self, uow: SqlUnitOfWork, tenant: UUID, actor: UUID) -> None:
        self.uow, self.session, self.tenant, self.actor = (
            uow,
            uow.session,
            tenant,
            actor,
        )

    async def lock_actor(self) -> None:
        await self.session.scalar(
            select(User).where(User.id == self.actor).with_for_update()
        )

    async def create_opportunity(
        self,
        title: str,
        customer_id: UUID,
        expected_on: date,
        lines: list[Line],
        key: UUID,
    ) -> Opportunity:
        await self.lock_actor()
        items: list[dict[str, str | int]] = [
            {
                "product_id": str(x.product_id),
                "quantity": x.quantity,
                "unit_price": str(x.unit_price),
            }
            for x in lines
        ]
        digest = fingerprint([title, customer_id, expected_on, items])
        existing = await self.session.scalar(
            select(Opportunity).where(Opportunity.request_key == key)
        )
        if existing:
            if existing.payload_hash != digest:
                raise BusinessError("Chave já usada com outros dados.")
            return existing
        customer = await self.session.scalar(
            select(Customer).where(Customer.id == customer_id)
        )
        products = list(
            await self.session.scalars(
                select(Product).where(Product.id.in_([x.product_id for x in lines]))
            )
        )
        if (
            not customer
            or customer.is_simulated
            or len(products) != len(lines)
            or any(p.is_simulated for p in products)
        ):
            raise BusinessError("Selecione cliente e produtos reais da sua empresa.")
        if expected_on < business_today():
            raise BusinessError("Previsão não pode ser passada.")
        row = Opportunity(
            tenant_id=self.tenant,
            title=title,
            customer_id=customer_id,
            stage="prospeccao",
            expected_on=expected_on,
            amount=total(lines),
            items=items,
            order_id=None,
            request_key=key,
            payload_hash=digest,
            is_simulated=False,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def change_stage(
        self, identity: UUID, version: int, stage: str
    ) -> Opportunity:
        row = await self.session.scalar(
            select(Opportunity).where(Opportunity.id == identity).with_for_update()
        )
        if row is None or row.is_simulated or row.order_id or row.version != version:
            raise BusinessError(
                "Oportunidade indisponível ou alterada. Atualize a tela."
            )
        stages = ["prospeccao", "proposta", "negociacao"]
        if (
            row.stage not in stages
            or abs(stages.index(row.stage) - stages.index(stage)) != 1
        ):
            raise BusinessError("Mova apenas para uma etapa adjacente.")
        row.stage = stage
        await self.session.flush()
        return row

    async def convert(self, identity: UUID, version: int) -> Opportunity:
        await self.lock_actor()
        row = await self.session.scalar(
            select(Opportunity).where(Opportunity.id == identity).with_for_update()
        )
        if row is None or row.is_simulated:
            raise BusinessError("Oportunidade real não encontrada.")
        if row.order_id:
            return row
        if row.version != version or row.stage != "negociacao":
            raise BusinessError("Atualize a oportunidade e avance até Negociação.")
        customer = await self.session.scalar(
            select(Customer).where(Customer.id == row.customer_id).with_for_update()
        )
        if customer is None or customer.is_simulated:
            raise BusinessError("Cliente indisponível.")
        if row.expected_on < business_today():
            raise BusinessError("Previsão vencida. Reagende a oportunidade.")
        lines = [
            Line(
                UUID(str(x["product_id"])),
                int(x["quantity"]),
                Decimal(str(x["unit_price"])),
            )
            for x in row.items
        ]
        order = cast(
            Order,
            await OrderService(self.uow.operations).create(
                self.actor,
                row.id,
                "sale",
                customer.name,
                business_today(),
                row.expected_on,
                lines,
                customer_id=customer.id,
            ),
        )
        row.order_id, row.stage = order.id, "fechado"
        await self.session.flush()
        return row

    async def import_batch(
        self,
        account: str,
        reference: str,
        entries: list[dict[str, str]],
        origin: str = "imported-json",
    ) -> BankBatch:
        await self.lock_actor()
        digest = fingerprint(entries)
        existing = await self.session.scalar(
            select(BankBatch).where(
                BankBatch.account == account, BankBatch.reference == reference
            )
        )
        if existing:
            if existing.payload_hash != digest:
                raise BusinessError("Referência já importada com dados diferentes.")
            return existing
        identifiers = [x["external_id"] for x in entries]
        if len(set(identifiers)) != len(entries):
            raise BusinessError("Identificadores externos repetidos no lote.")
        row = BankBatch(
            tenant_id=self.tenant,
            account=account,
            reference=reference,
            payload_hash=digest,
            origin=origin,
            is_simulated=False,
        )
        self.session.add(row)
        await self.session.flush()
        for entry in entries:
            self.session.add(
                BankTransaction(
                    tenant_id=self.tenant,
                    batch_id=row.id,
                    account=account,
                    external_id=entry["external_id"],
                    posted_on=date.fromisoformat(entry["posted_on"]),
                    description=entry["description"],
                    amount=Decimal(entry["amount"]),
                    cash_entry_id=None,
                    matched_at=None,
                    is_simulated=False,
                )
            )
        await self.session.flush()
        return row

    @staticmethod
    def conditions(row: BankTransaction) -> list[ColumnElement[bool]]:
        return [
            CashEntry.amount == abs(row.amount),
            CashEntry.kind == ("receita" if row.amount > 0 else "despesa"),
            CashEntry.effective_on >= row.posted_on - timedelta(days=3),
            CashEntry.effective_on <= row.posted_on + timedelta(days=3),
            CashEntry.status != "aguardando_aprovacao",
            CashEntry.is_simulated == row.is_simulated,
        ]

    async def match(self, identity: UUID, cash_id: UUID) -> BankTransaction:
        row = await self.session.scalar(
            select(BankTransaction)
            .where(BankTransaction.id == identity)
            .with_for_update()
        )
        if row is None or row.is_simulated:
            raise BusinessError("Movimento real não encontrado.")
        if row.cash_entry_id:
            if row.cash_entry_id == cash_id:
                return row
            raise BusinessError("Movimento já conciliado.")
        cash = await self.session.scalar(
            select(CashEntry)
            .where(CashEntry.id == cash_id, *self.conditions(row))
            .with_for_update()
        )
        if cash is None:
            raise BusinessError("Valor, direção, data ou aprovação incompatível.")
        if await self.session.scalar(
            select(BankTransaction).where(BankTransaction.cash_entry_id == cash.id)
        ):
            raise BusinessError("Lançamento já conciliado.")
        if cash.status == "pendente":
            cash.status = "concluido"
            cash.settled_on = row.posted_on
            cash.effective_on = row.posted_on
        row.cash_entry_id, row.matched_at = cash.id, utcnow()
        await self.session.flush()
        return row
