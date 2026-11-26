from datetime import date
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from erp.modules.financeiro.application.cash import CashService
from erp.modules.financeiro.domain.cash import (
    EntryFilter,
    InvalidEntry,
    IdempotencyConflict,
)
from erp.modules.financeiro.presentation.schemas.cash import (
    CreateEntry,
    EntryResponse,
    PageResponse,
    SummaryResponse,
)
from sqlalchemy import select
from erp.modules.financeiro.infrastructure.models import CashEntry
from erp.modules.financeiro.infrastructure.repositories.cash import view
from erp.presentation.dependencies import authenticated_uow, require_permissions
from erp.shared.domain.security import Principal
from erp.shared.infrastructure.database.uow import SqlUnitOfWork

router = APIRouter(prefix="/financeiro", tags=["financeiro"])
ReadPrincipal = Annotated[
    Principal, Depends(require_permissions("financeiro:lancamento:ler"))
]
WritePrincipal = Annotated[
    Principal, Depends(require_permissions("financeiro:lancamento:escrever"))
]
Uow = Annotated[SqlUnitOfWork, Depends(authenticated_uow)]


def filters(
    start_date: date,
    end_date: date,
    source: Literal["real", "demo"] = "real",
    status: Literal["pendente", "concluido", "aguardando_aprovacao"] | None = None,
    kind: Literal["receita", "despesa"] | None = None,
    q: Annotated[str, Query(max_length=100)] = "",
    category: Annotated[str | None, Query(max_length=40)] = None,
    sort: str = "effective_on",
    desc: bool = True,
) -> EntryFilter:
    result = EntryFilter(
        start_date, end_date, source, status, kind, q.strip(), category, sort, desc
    )
    try:
        result.validate()
    except InvalidEntry as exc:
        raise HTTPException(422, str(exc)) from exc
    return result


@router.get("/lancamentos", response_model=PageResponse)
async def list_entries(
    principal: ReadPrincipal,
    uow: Uow,
    selection: Annotated[EntryFilter, Depends(filters)],
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
) -> PageResponse:
    return PageResponse.model_validate(
        await CashService(uow.cash).page(selection, page, page_size)
    )


@router.get("/lancamentos/{entry_id}", response_model=EntryResponse)
async def entry(entry_id: UUID, principal: ReadPrincipal, uow: Uow) -> EntryResponse:
    row = await uow.session.scalar(select(CashEntry).where(CashEntry.id == entry_id))
    if row is None:
        raise HTTPException(404, "Lançamento indisponível.")
    return EntryResponse.model_validate(view(row))


@router.get("/fluxo-caixa", response_model=SummaryResponse)
async def cash_flow(
    principal: ReadPrincipal,
    uow: Uow,
    selection: Annotated[EntryFilter, Depends(filters)],
) -> SummaryResponse:
    return SummaryResponse.model_validate(
        await CashService(uow.cash).summary(selection)
    )


@router.post("/lancamentos", response_model=EntryResponse, status_code=201)
async def create_entry(
    body: CreateEntry,
    principal: WritePrincipal,
    uow: Uow,
    response: Response,
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> EntryResponse:
    try:
        result, created = await CashService(uow.cash).create(
            body.command(), principal.user_id, key
        )
        await uow.commit()
    except InvalidEntry as exc:
        raise HTTPException(422, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(
            409, "Esta chave já foi utilizada com outros dados."
        ) from exc
    response.status_code = 201 if created else 200
    response.headers["Cache-Control"] = "no-store"
    return EntryResponse.model_validate(result)
