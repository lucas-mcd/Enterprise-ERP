from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated
from uuid import uuid4
from erp.modules.identity.infrastructure.tokens import Tokens
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.exceptions import RedisError
from erp.config import settings
from erp.shared.domain.security import Forbidden, Principal, authorize
from erp.shared.infrastructure.database.context import AuditContext
from erp.shared.infrastructure.database.uow import SqlUnitOfWork

bearer = HTTPBearer(auto_error=False)


async def authenticated_uow(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AsyncIterator[SqlUnitOfWork]:
    if credentials is None:
        raise HTTPException(401, "Bearer token required")
    cfg = settings()
    try:
        identity = Tokens(cfg).decode(credentials.credentials)
        user_id, tenant_id, sid = (
            identity.user_id,
            identity.tenant_id,
            identity.session_id,
        )
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError) as exc:
        raise HTTPException(
            401, "Invalid access token", headers={"WWW-Authenticate": "Bearer"}
        ) from exc
    try:
        active = await request.app.state.redis.get(f"session:{tenant_id}:{sid}")
    except RedisError as exc:
        raise HTTPException(503, "Session service unavailable") from exc
    if active != str(user_id):
        raise HTTPException(401, "Session expired or revoked")
    ctx = AuditContext(
        tenant_id,
        user_id,
        "user",
        uuid4(),
        request.client.host if request.client else None,
        request.headers.get("user-agent", "")[:512],
    )
    async with SqlUnitOfWork(request.app.state.sessions, ctx) as uow:
        principal = await uow.identities.principal(user_id)
        if principal is None or not await uow.identities.tenant_active():
            raise HTTPException(401, "Inactive user")
        request.state.session_id = sid
        request.state.principal = principal
        yield uow


async def get_current_user(
    request: Request, uow: Annotated[SqlUnitOfWork, Depends(authenticated_uow)]
) -> Principal:
    principal: Principal = request.state.principal
    return principal


def require_permissions(*actions: str) -> Callable[..., Awaitable[Principal]]:
    if not actions:
        raise ValueError("Specify at least one permission")

    async def dependency(
        principal: Annotated[Principal, Depends(get_current_user)],
    ) -> Principal:
        try:
            for action in actions:
                authorize(principal, action)
        except Forbidden as exc:
            raise HTTPException(403, "Permission denied") from exc
        return principal

    return dependency


def require_permission(action: str) -> Callable[..., Awaitable[Principal]]:
    return require_permissions(action)
