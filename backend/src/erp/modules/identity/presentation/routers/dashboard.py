from typing import Annotated
from erp.modules.identity.application.dashboard import GetDashboard
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from erp.presentation.dependencies import authenticated_uow, require_permissions
from erp.shared.domain.security import Principal
from erp.shared.infrastructure.database.uow import SqlUnitOfWork

router = APIRouter(prefix="/identity", tags=["identity"])


class StrictResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", from_attributes=True)


class ActivityResponse(StrictResponse):
    code: str
    category: str
    description: str
    status: str
    amount: str


class AuditResponse(StrictResponse):
    id: str
    table: str
    operation: str
    occurred_at: str


class DashboardResponse(StrictResponse):
    tenant_name: str
    is_simulated: bool = True
    total_records: int
    completed: int
    total_amount: str
    activities: list[ActivityResponse]
    audit: list[AuditResponse]


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    principal: Annotated[
        Principal, Depends(require_permissions("identidade:dashboard:ler"))
    ],
    uow: Annotated[SqlUnitOfWork, Depends(authenticated_uow)],
) -> DashboardResponse:
    snapshot = await GetDashboard(uow.dashboard).execute(principal)
    return DashboardResponse.model_validate(snapshot)
