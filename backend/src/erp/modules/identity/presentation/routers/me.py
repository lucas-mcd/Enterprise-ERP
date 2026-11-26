from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from erp.presentation.dependencies import require_permission
from erp.shared.domain.security import Principal

router = APIRouter(prefix="/identity", tags=["identity"])


class MeResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    user_id: UUID
    tenant_id: UUID
    permissions: list[str]


@router.get("/me", response_model=MeResponse)
async def me(
    principal: Annotated[
        Principal, Depends(require_permission("identidade:perfil:ler"))
    ],
) -> MeResponse:
    return MeResponse(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        permissions=sorted(principal.permissions),
    )
