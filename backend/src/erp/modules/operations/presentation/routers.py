import asyncio
from fastapi.responses import StreamingResponse
from erp.modules.reports.infrastructure.render import grid_file
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal, cast
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, or_
from erp.presentation.dependencies import authenticated_uow, require_permissions
from erp.shared.domain.security import Principal
from erp.shared.infrastructure.database.uow import SqlUnitOfWork
from erp.modules.operations.domain.orders import Line, BusinessError
from erp.modules.operations.application.service import OrderService
from erp.modules.operations.infrastructure.models import (
    Product,
    Order,
    OrderLine,
    StockMovement,
    Supplier,
)

Uow = Annotated[SqlUnitOfWork, Depends(authenticated_uow)]
Key = Annotated[UUID, Header(alias="Idempotency-Key")]


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True)


class ProductInput(Strict):
    sku: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=3, max_length=160)
    category: str = Field(min_length=2, max_length=40)
    minimum: int = Field(ge=0, le=1000000)


class MovementInput(Strict):
    quantity: int = Field(ge=-100000, le=100000)
    reason: str = Field(min_length=5, max_length=180)


class LineInput(Strict):
    product_id: str
    quantity: int = Field(ge=1, le=100000)
    unit_price: str = Field(pattern=r"^(?:0|[1-9]\d{0,8})\.\d{2}$")

    @field_validator("product_id")
    @classmethod
    def uuid_value(cls, value: str) -> str:
        return str(UUID(value))


class OrderInput(Strict):
    customer_id: str | None = None

    @field_validator("customer_id")
    @classmethod
    def customer_uuid(cls, value: str | None) -> str | None:
        return str(UUID(value)) if value is not None else None

    variable_cost: str = Field(default="0.00", pattern=r"^[0-9]{1,9}\.[0-9]{2}$")
    counterparty: str = Field(min_length=2, max_length=120)
    ordered_on: str
    due_date: str
    lines: list[LineInput] = Field(min_length=1, max_length=50)

    @field_validator("ordered_on", "due_date")
    @classmethod
    def date_value(cls, value: str) -> str:
        return date.fromisoformat(value).isoformat()


stock = APIRouter(prefix="/estoque", tags=["estoque"])
ReadStock = Annotated[Principal, Depends(require_permissions("estoque:saldo:ler"))]
WriteStock = Annotated[
    Principal, Depends(require_permissions("estoque:movimento:escrever"))
]


@stock.get("/produtos")
async def products(
    principal: ReadStock,
    uow: Uow,
    source: Literal["real", "demo"] = "real",
    q: str = "",
    category: str = "",
    low: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    sort: str = "name",
    desc: bool = False,
) -> dict[str, Any]:
    where: list[Any] = [Product.is_simulated.is_(source == "demo")]
    if q:
        where.append(
            or_(
                Product.name.icontains(q[:100], autoescape=True),
                Product.sku.icontains(q[:100], autoescape=True),
            )
        )
    if category:
        where.append(Product.category == category)
    if low:
        where.append(Product.balance <= Product.minimum)
    return await uow.operations.page(Product, where, page, page_size, sort, desc)


@stock.post("/produtos", status_code=201)
async def create_product(
    body: ProductInput, principal: WriteStock, uow: Uow
) -> dict[str, Any]:
    sku = body.sku.upper()
    if await uow.session.scalar(select(Product).where(Product.sku == sku)):
        raise BusinessError("SKU já cadastrado.")
    row = Product(
        tenant_id=principal.tenant_id,
        sku=sku,
        name=body.name,
        category=body.category,
        minimum=body.minimum,
        balance=0,
        is_simulated=False,
    )
    uow.session.add(row)
    await uow.commit()
    return uow.operations.view(row)


@stock.post("/produtos/{product_id}/movimentos", status_code=201)
async def movement(
    product_id: UUID, body: MovementInput, principal: WriteStock, uow: Uow, key: Key
) -> dict[str, Any]:
    row = await uow.session.scalar(
        select(Product).where(Product.id == product_id).with_for_update()
    )
    if row is None or row.is_simulated or body.quantity == 0:
        raise BusinessError("Produto real ou quantidade inválida.")
    result = await uow.operations.move(row, body.quantity, body.reason, key)
    await uow.commit()
    return uow.operations.view(result)


@stock.get("/produtos/{product_id}/movimentos")
async def movements(
    product_id: UUID,
    principal: ReadStock,
    uow: Uow,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> dict[str, Any]:
    return await uow.operations.page(
        StockMovement,
        [StockMovement.product_id == product_id],
        page,
        page_size,
        "created_at",
        True,
    )


async def export_page(
    data: dict[str, Any], fields: list[str], labels: list[str], format: str
) -> StreamingResponse:
    if data["total"] > 5000 or len(data["items"]) > 5000:
        raise BusinessError("Exportação limitada a 5.000 registros. Reduza os filtros.")
    rows = [[str(row.get(field, "")) for field in fields] for row in data["items"]]
    numeric = {
        index
        for index, field in enumerate(fields)
        if field in ("balance", "minimum", "total")
    }
    content = await asyncio.to_thread(grid_file, labels, rows, format, numeric)
    media = (
        "text/csv; charset=utf-8"
        if format == "csv"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return StreamingResponse(
        iter([content]),
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="registros.{format}"',
            "Cache-Control": "no-store",
        },
    )


@stock.get("/exportar")
async def export_products(
    principal: ReadStock,
    uow: Uow,
    source: Literal["real", "demo"] = "real",
    q: str = "",
    category: str = "",
    low: bool = False,
    sort: str = "name",
    desc: bool = False,
    format: Literal["csv", "xlsx"] = "csv",
) -> StreamingResponse:
    data = await products(principal, uow, source, q, category, low, 1, 5001, sort, desc)
    return await export_page(
        data,
        ["sku", "name", "category", "balance", "minimum"],
        ["SKU", "Produto", "Categoria", "Saldo un.", "Mínimo un."],
        format,
    )


def order_router(prefix: str, kind: str, permission: str) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[permission])
    read = require_permissions(f"{permission}:pedido:ler")
    write = require_permissions(f"{permission}:pedido:escrever")

    if kind == "purchase":

        @router.get("/fornecedores")
        async def suppliers(
            uow: Uow, principal: Principal = Depends(read), q: str = ""
        ) -> list[dict[str, Any]]:
            rows = await uow.session.scalars(
                select(Supplier)
                .where(Supplier.name.icontains(q[:100], autoescape=True))
                .order_by(Supplier.name)
                .limit(100)
            )
            return [{"id": row.id, "name": row.name} for row in rows]

    @router.get("/pedidos")
    async def orders(
        uow: Uow,
        principal: Principal = Depends(read),
        source: Literal["real", "demo"] = "real",
        q: str = "",
        status: (
            Literal["draft", "completed", "aguardando_aprovacao", "cancelled"] | None
        ) = None,
        start_date: date | None = None,
        end_date: date | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        sort: str = "ordered_on",
        desc: bool = True,
    ) -> dict[str, Any]:
        where: list[Any] = [
            Order.kind == kind,
            Order.is_simulated.is_(source == "demo"),
        ]
        if q:
            try:
                order_id = UUID(q)
            except ValueError:
                where.append(Order.counterparty.icontains(q[:100], autoescape=True))
            else:
                where.append(Order.id == order_id)
        if status:
            where.append(Order.status == status)
        if start_date:
            where.append(Order.ordered_on >= start_date)
        if end_date:
            where.append(Order.ordered_on <= end_date)
        return await uow.operations.page(Order, where, page, page_size, sort, desc)

    @router.post("/pedidos", status_code=201)
    async def create(
        body: OrderInput, uow: Uow, key: Key, principal: Principal = Depends(write)
    ) -> dict[str, Any]:
        result = await OrderService(uow.operations).create(
            principal.user_id,
            key,
            kind,
            body.counterparty,
            date.fromisoformat(body.ordered_on),
            date.fromisoformat(body.due_date),
            [
                Line(UUID(x.product_id), x.quantity, Decimal(x.unit_price))
                for x in body.lines
            ],
            Decimal(body.variable_cost),
            UUID(body.customer_id) if body.customer_id else None,
        )
        await uow.commit()
        return uow.operations.view(cast(Order, result))

    @router.get("/pedidos/{order_id}")
    async def detail(
        order_id: UUID, uow: Uow, principal: Principal = Depends(read)
    ) -> dict[str, Any]:
        order = await uow.session.scalar(
            select(Order).where(Order.kind == kind, Order.id == order_id)
        )
        if order is None:
            raise HTTPException(404, "Pedido não encontrado.")
        lines = await uow.session.execute(
            select(OrderLine, Product)
            .join(Product, Product.id == OrderLine.product_id)
            .where(OrderLine.order_id == order_id)
            .order_by(Product.sku)
        )
        return {
            **uow.operations.view(order),
            "created_at": order.created_at,
            "items": [
                {
                    "sku": product.sku,
                    "name": product.name,
                    "quantity": line.quantity,
                    "unit_price": str(line.unit_price),
                }
                for line, product in lines
            ],
        }

    @router.post("/pedidos/{order_id}/cancelar")
    async def cancel(
        order_id: UUID, uow: Uow, principal: Principal = Depends(write)
    ) -> dict[str, Any]:
        order = await uow.session.scalar(
            select(Order)
            .where(Order.kind == kind, Order.id == order_id)
            .with_for_update()
        )
        if order is None or order.is_simulated:
            raise HTTPException(404, "Pedido indisponível.")
        if order.status not in ("draft", "cancelled"):
            raise BusinessError("Apenas rascunhos podem ser cancelados.")
        order.status = "cancelled"
        await uow.commit()
        return uow.operations.view(order)

    @router.post("/pedidos/{order_id}/concluir")
    async def complete(
        order_id: UUID, uow: Uow, principal: Principal = Depends(write)
    ) -> dict[str, Any]:
        result = await OrderService(uow.operations).complete(
            order_id, kind, principal.user_id
        )
        await uow.commit()
        return uow.operations.view(cast(Order, result))

    @router.get("/exportar")
    async def export_orders(
        uow: Uow,
        principal: Principal = Depends(read),
        source: Literal["real", "demo"] = "real",
        q: str = "",
        status: (
            Literal["draft", "completed", "aguardando_aprovacao", "cancelled"] | None
        ) = None,
        start_date: date | None = None,
        end_date: date | None = None,
        sort: str = "ordered_on",
        desc: bool = True,
        format: Literal["csv", "xlsx"] = "csv",
    ) -> StreamingResponse:
        data = await orders(
            uow, principal, source, q, status, start_date, end_date, 1, 5001, sort, desc
        )
        return await export_page(
            data,
            [
                "id",
                "counterparty",
                "ordered_on",
                "due_date",
                "status",
                "total",
                "cash_entry_id",
            ],
            [
                "Pedido",
                "Contraparte",
                "Data",
                "Vencimento",
                "Status",
                "Total BRL",
                "Lançamento financeiro",
            ],
            format,
        )

    return router
