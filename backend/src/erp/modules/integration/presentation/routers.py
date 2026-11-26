from decimal import Decimal
from datetime import date
from typing import Annotated, Literal, cast
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.sql.elements import ColumnElement
from erp.modules.integration.infrastructure.models import (
    Customer,
    Opportunity,
    CostCenter,
    BankBatch,
    BankTransaction,
)
from erp.modules.integration.application.services import IntegrationService
from erp.modules.integration.presentation.schemas import (
    CustomerInput,
    OpportunityInput,
    StageInput,
    VersionInput,
    RevisionInput,
    StatementInput,
    SimulateInput,
    MatchInput,
)
from erp.modules.operations.domain.orders import Line
from erp.modules.operations.infrastructure.models import Product, Order
from erp.modules.financeiro.infrastructure.models import CashEntry
from erp.modules.financeiro.domain.cash import business_today
from erp.presentation.dependencies import (
    authenticated_uow,
    require_permissions,
    get_current_user,
)
from erp.shared.domain.security import Principal
from erp.shared.infrastructure.database.uow import SqlUnitOfWork
from erp.shared.infrastructure.database.base import Entity, utcnow

router = APIRouter(tags=["CRM, Tesouraria e Alertas"])
Uow = Annotated[SqlUnitOfWork, Depends(authenticated_uow)]
Reader = Annotated[Principal, Depends(require_permissions("vendas:pedido:ler"))]
Writer = Annotated[Principal, Depends(require_permissions("vendas:pedido:escrever"))]
Reconciler = Annotated[
    Principal, Depends(require_permissions("financeiro:conciliacao:executar"))
]


def view(row: Entity) -> dict[str, object]:
    fields = {
        "crm_customers": (
            "id",
            "name",
            "document",
            "segment",
            "email",
            "phone",
            "credit_limit",
            "version",
            "is_simulated",
        ),
        "crm_opportunities": (
            "id",
            "title",
            "customer_id",
            "stage",
            "loss_reason",
            "expected_on",
            "amount",
            "items",
            "order_id",
            "version",
            "is_simulated",
        ),
        "bank_transactions": (
            "id",
            "account",
            "external_id",
            "posted_on",
            "description",
            "amount",
            "cash_entry_id",
            "matched_at",
            "is_simulated",
        ),
    }
    values = {key: getattr(row, key) for key in fields[row.__tablename__]}
    return {
        key: format(value, ".2f") if isinstance(value, Decimal) else value
        for key, value in values.items()
    }


@router.get("/crm/clientes")
async def customers(
    uow: Uow,
    principal: Reader,
    source: Literal["real", "demo"] = "real",
    q: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> dict[str, object]:
    where = [
        Customer.is_simulated.is_(source == "demo"),
        Customer.name.icontains(q, autoescape=True),
    ]
    rows = await uow.session.scalars(
        select(Customer)
        .where(*where)
        .order_by(Customer.name, Customer.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    count = await uow.session.scalar(
        select(func.count()).select_from(Customer).where(*where)
    )
    return {"items": [view(x) for x in rows], "total": count}


@router.post("/crm/clientes", status_code=201)
async def create_customer(
    body: CustomerInput, uow: Uow, principal: Writer
) -> dict[str, object]:
    row = Customer(
        tenant_id=principal.tenant_id,
        **body.model_dump(exclude={"credit_limit"}),
        credit_limit=Decimal(body.credit_limit),
        is_simulated=False,
    )
    uow.session.add(row)
    await uow.session.flush()
    result = view(row)
    await uow.commit()
    return result


@router.put("/crm/clientes/{identity}")
async def update_customer(
    identity: UUID,
    body: CustomerInput,
    uow: Uow,
    principal: Writer,
    version: int = Query(ge=1),
) -> dict[str, object]:
    row = await uow.session.scalar(
        select(Customer).where(Customer.id == identity).with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Cliente não encontrado.")
    if row.is_simulated or row.version != version:
        raise HTTPException(409, "Cliente de demonstração ou alterado.")
    for key, value in body.model_dump(exclude={"credit_limit"}).items():
        setattr(row, key, value)
    row.credit_limit = Decimal(body.credit_limit)
    await uow.session.flush()
    result = view(row)
    await uow.commit()
    return result


@router.get("/crm/oportunidades")
async def opportunities(
    uow: Uow,
    principal: Reader,
    source: Literal["real", "demo"] = "real",
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
) -> dict[str, object]:
    condition = Opportunity.is_simulated.is_(source == "demo")
    rows = await uow.session.scalars(
        select(Opportunity)
        .where(condition)
        .order_by(Opportunity.created_at.desc(), Opportunity.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    count = await uow.session.scalar(
        select(func.count()).select_from(Opportunity).where(condition)
    )
    return {"items": [view(x) for x in rows], "total": count}


@router.post("/crm/oportunidades", status_code=201)
async def create_opportunity(
    body: OpportunityInput,
    uow: Uow,
    principal: Writer,
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    row = await IntegrationService(
        uow, principal.tenant_id, principal.user_id
    ).create_opportunity(
        body.title,
        UUID(body.customer_id),
        date.fromisoformat(body.expected_on),
        [
            Line(UUID(x.product_id), x.quantity, Decimal(x.unit_price))
            for x in body.items
        ],
        key,
    )
    result = view(row)
    await uow.commit()
    return result


@router.patch("/crm/oportunidades/{identity}/etapa")
async def stage(
    identity: UUID, body: StageInput, uow: Uow, principal: Writer
) -> dict[str, object]:
    row = await IntegrationService(
        uow, principal.tenant_id, principal.user_id
    ).change_stage(identity, body.version, body.stage)
    result = view(row)
    await uow.commit()
    return result


@router.patch("/crm/oportunidades/{identity}/revisar")
async def revise(
    identity: UUID, body: RevisionInput, uow: Uow, principal: Writer
) -> dict[str, object]:
    row = await uow.session.scalar(
        select(Opportunity).where(Opportunity.id == identity).with_for_update()
    )
    if (
        row is None
        or row.is_simulated
        or row.version != body.version
        or row.stage in ("fechado", "perdido")
    ):
        raise HTTPException(409, "Oportunidade indisponível ou alterada.")
    if bool(body.expected_on) == bool(body.loss_reason):
        raise HTTPException(422, "Informe a previsão ou o motivo da perda.")
    if body.expected_on:
        try:
            expected = date.fromisoformat(body.expected_on)
        except ValueError as exc:
            raise HTTPException(422, "Data inválida.") from exc
        if expected < business_today():
            raise HTTPException(422, "Escolha uma previsão atual ou futura.")
        row.expected_on = expected
    else:
        row.stage, row.loss_reason = "perdido", body.loss_reason
    await uow.session.flush()
    result = view(row)
    await uow.commit()
    return result


@router.post("/crm/oportunidades/{identity}/converter")
async def convert(
    identity: UUID, body: VersionInput, uow: Uow, principal: Writer
) -> dict[str, object]:
    row = await IntegrationService(uow, principal.tenant_id, principal.user_id).convert(
        identity, body.version
    )
    result = view(row)
    await uow.commit()
    return result


@router.get("/financeiro/centros-custo")
async def centers(
    uow: Uow,
    principal: Annotated[
        Principal, Depends(require_permissions("financeiro:lancamento:ler"))
    ],
) -> list[dict[str, object]]:
    return [
        {"id": x.id, "name": x.name}
        for x in await uow.session.scalars(select(CostCenter).order_by(CostCenter.name))
    ]


@router.post("/financeiro/conciliacao/importar", status_code=201)
async def import_batch(
    body: StatementInput, uow: Uow, principal: Reconciler
) -> dict[str, object]:
    row = await IntegrationService(
        uow, principal.tenant_id, principal.user_id
    ).import_batch(body.account, body.reference, [x.model_dump() for x in body.entries])
    result: dict[str, object] = {"id": row.id, "reference": row.reference}
    await uow.commit()
    return result


@router.post("/financeiro/conciliacao/simular", status_code=201)
async def simulate(
    body: SimulateInput, uow: Uow, principal: Reconciler
) -> dict[str, object]:
    account = "SIMULADOR-LOCAL"
    existing = await uow.session.scalar(
        select(BankBatch).where(
            BankBatch.account == account, BankBatch.reference == body.reference
        )
    )
    if existing:
        return {"id": existing.id, "reference": existing.reference}
    rows = await uow.session.scalars(
        select(CashEntry)
        .where(
            CashEntry.is_simulated.is_(False),
            CashEntry.effective_on <= business_today(),
            CashEntry.status != "aguardando_aprovacao",
        )
        .order_by(CashEntry.effective_on.desc(), CashEntry.id)
        .limit(500)
    )
    used = set(
        await uow.session.scalars(
            select(BankTransaction.external_id).where(
                BankTransaction.account == account
            )
        )
    )
    entries = [
        {
            "external_id": f"sim:{x.id}",
            "posted_on": x.effective_on.isoformat(),
            "description": x.description,
            "amount": str(x.amount if x.kind == "receita" else -x.amount),
        }
        for x in rows
        if f"sim:{x.id}" not in used
    ][:20]
    if not entries:
        raise HTTPException(409, "Não há lançamentos reais elegíveis.")
    row = await IntegrationService(
        uow, principal.tenant_id, principal.user_id
    ).import_batch(account, body.reference, entries, "simulated-local")
    result: dict[str, object] = {"id": row.id, "reference": row.reference}
    await uow.commit()
    return result


@router.get("/financeiro/conciliacao/movimentos")
async def movements(
    uow: Uow,
    principal: Reconciler,
    source: Literal["real", "demo"] = "real",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, object]:
    condition = BankTransaction.is_simulated.is_(source == "demo")
    rows = await uow.session.scalars(
        select(BankTransaction)
        .where(condition)
        .order_by(BankTransaction.posted_on.desc(), BankTransaction.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    count = await uow.session.scalar(
        select(func.count()).select_from(BankTransaction).where(condition)
    )
    return {"items": [view(x) for x in rows], "total": count}


@router.get("/financeiro/conciliacao/movimentos/{identity}/candidatos")
async def candidates(
    identity: UUID, uow: Uow, principal: Reconciler
) -> list[dict[str, object]]:
    row = await uow.session.scalar(
        select(BankTransaction).where(BankTransaction.id == identity)
    )
    if row is None:
        raise HTTPException(404, "Movimento não encontrado.")
    linked = select(BankTransaction.cash_entry_id).where(
        BankTransaction.cash_entry_id.is_not(None)
    )
    rows = await uow.session.scalars(
        select(CashEntry)
        .where(*IntegrationService.conditions(row), CashEntry.id.not_in(linked))
        .order_by(CashEntry.effective_on, CashEntry.id)
        .limit(50)
    )
    return [
        {
            "id": x.id,
            "description": x.description,
            "amount": str(x.amount),
            "effective_on": x.effective_on,
        }
        for x in rows
    ]


@router.post("/financeiro/conciliacao/movimentos/{identity}/conciliar")
async def match(
    identity: UUID, body: MatchInput, uow: Uow, principal: Reconciler
) -> dict[str, object]:
    row = await IntegrationService(uow, principal.tenant_id, principal.user_id).match(
        identity, UUID(body.cash_entry_id)
    )
    result = view(row)
    await uow.commit()
    return result


@router.get("/notificacoes")
async def notifications(
    uow: Uow, principal: Annotated[Principal, Depends(get_current_user)]
) -> dict[str, object]:
    items: list[dict[str, object]] = []
    count = 0
    definitions: list[
        tuple[
            str,
            type[Product] | type[Order] | type[CashEntry],
            ColumnElement[bool],
            str,
            str,
        ]
    ] = [
        (
            "estoque:saldo:ler",
            Product,
            Product.balance <= Product.minimum,
            "Estoque crítico",
            "/app/estoque",
        ),
        (
            "compras:pedido:ler",
            Order,
            (Order.kind == "purchase") & (Order.status == "aguardando_aprovacao"),
            "Compra aguardando aprovação",
            "/app/compras",
        ),
        (
            "financeiro:lancamento:ler",
            CashEntry,
            (CashEntry.status == "pendente") & (CashEntry.due_date == business_today()),
            "Conta vencendo hoje",
            "/app/financeiro",
        ),
    ]
    for permission, model, condition, title, path in definitions:
        if permission not in principal.permissions:
            continue
        where = [condition, model.is_simulated.is_(False)]
        count += int(
            await uow.session.scalar(
                select(func.count()).select_from(model).where(*where)
            )
            or 0
        )
        rows = await uow.session.scalars(
            select(model)
            .where(*where)
            .order_by(model.created_at.desc(), model.id)
            .limit(10)
        )
        for row in rows:
            description = (
                row.name
                if isinstance(row, Product)
                else (
                    row.counterparty
                    if isinstance(row, Order)
                    else cast(CashEntry, row).description
                )
            )
            items.append(
                {
                    "id": f"{model.__tablename__}:{row.id}",
                    "title": title,
                    "description": description,
                    "path": path,
                }
            )
    return {"total": count, "items": items, "updated_at": utcnow()}
