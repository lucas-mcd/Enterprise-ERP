from typing import Annotated
from uuid import UUID, uuid4
from dataclasses import replace
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from redis.exceptions import RedisError
from erp.config import settings
from erp.modules.identity.application.use_cases.login import Login
from erp.modules.identity.domain.auth import InvalidCredentials
from erp.modules.identity.infrastructure.passwords import password_service
from erp.modules.identity.infrastructure.sessions import (
    RateLimited,
    RedisSessions,
    RefreshSessions,
    parse_refresh,
)
from erp.modules.identity.infrastructure.tokens import Tokens
from erp.modules.identity.presentation.schemas.auth import (
    LoginRequest,
    LoginResponse,
    UserResponse,
)
from erp.presentation.dependencies import get_current_user
from erp.shared.domain.security import Principal
from erp.shared.infrastructure.database.context import AuditContext
from erp.shared.infrastructure.database.uow import SqlUnitOfWork

router = APIRouter(prefix="/identity/auth", tags=["authentication"])


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest, request: Request, response: Response
) -> LoginResponse:
    cfg = settings()
    check_origin(request)
    tenant, sid = UUID(body.tenant_id), uuid4()
    sessions = RefreshSessions(
        request.app.state.redis, cfg.jwt_secret.get_secret_value()
    )
    ip = request.client.host if request.client else "unknown"
    try:
        await sessions.limit(f"ip:{ip}", maximum=60)
        await sessions.limit(f"account:{tenant}:{body.email}", maximum=10)
    except RateLimited as exc:
        raise HTTPException(
            429,
            "Muitas tentativas. Aguarde e tente novamente.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except RedisError as exc:
        raise HTTPException(503, "Serviço de autenticação indisponível.") from exc
    ctx = AuditContext(
        tenant,
        None,
        "service",
        uuid4(),
        ip,
        request.headers.get("user-agent", "")[:512],
    )
    async with SqlUnitOfWork(request.app.state.sessions, ctx) as uow:
        try:
            authenticated = await Login(uow.identities, password_service()).execute(
                str(body.email), body.password.get_secret_value()
            )
        except InvalidCredentials as exc:
            raise HTTPException(
                401,
                "Empresa, email ou senha inválidos.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        principal = authenticated.principal
        uow.session.info["audit_context"] = replace(
            ctx, actor_id=principal.user_id, actor_kind="user"
        )
        # Commit optional rehash first. Never return a token on Redis failure.
        await uow.commit()
        token = Tokens(cfg).issue(principal, sid)
        try:
            refresh_token = await sessions.start(
                tenant,
                sid,
                principal.user_id,
                cfg.access_token_seconds,
                cfg.refresh_token_seconds,
            )
            set_refresh_cookie(response, refresh_token, cfg.refresh_token_seconds)
        except RedisError as exc:
            raise HTTPException(503, "Serviço de autenticação indisponível.") from exc
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        account = authenticated.account
        return LoginResponse(
            access_token=token,
            expires_in=cfg.access_token_seconds,
            user=UserResponse(
                user_id=principal.user_id,
                tenant_id=tenant,
                email=account.email,
                display_name=account.display_name,
                permissions=sorted(principal.permissions),
            ),
        )


@router.post("/logout", status_code=204)
async def logout(
    request: Request, principal: Annotated[Principal, Depends(get_current_user)]
) -> Response:
    cfg = settings()
    try:
        await RedisSessions(
            request.app.state.redis, cfg.jwt_secret.get_secret_value()
        ).revoke(principal.tenant_id, request.state.session_id)
    except RedisError as exc:
        raise HTTPException(503, "Não foi possível revogar a sessão.") from exc
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(
        "erp_refresh",
        path="/api/v1/identity/auth",
        secure=cfg.refresh_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return response


def check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != settings().public_origin.rstrip("/"):
        raise HTTPException(403, "Origem não autorizada.")


def set_refresh_cookie(response: Response, value: str, ttl: int) -> None:
    response.set_cookie(
        "erp_refresh",
        value,
        max_age=ttl,
        httponly=True,
        secure=settings().refresh_cookie_secure,
        samesite="strict",
        path="/api/v1/identity/auth",
    )
    response.headers["Cache-Control"] = "no-store"


@router.post("/refresh", response_model=LoginResponse)
async def refresh(request: Request, response: Response) -> LoginResponse:
    check_origin(request)
    if request.headers.get("x-erp-refresh") != "1":
        raise HTTPException(403, "Cabeçalho de renovação obrigatório.")
    cfg = settings()
    sessions = RefreshSessions(
        request.app.state.redis, cfg.jwt_secret.get_secret_value()
    )
    try:
        tenant, sid, secret = parse_refresh(request.cookies.get("erp_refresh", ""))
        user_id = await sessions.user(tenant, sid)
        if user_id is None:
            raise ValueError("Session missing")
        ctx = AuditContext(
            tenant,
            user_id,
            "user",
            uuid4(),
            request.client.host if request.client else None,
            request.headers.get("user-agent", "")[:512],
        )
        async with SqlUnitOfWork(request.app.state.sessions, ctx) as uow:
            principal = await uow.identities.principal(user_id)
            if principal is None or not await uow.identities.tenant_active():
                await sessions.revoke(tenant, sid)
                raise ValueError("Inactive account")
            from erp.modules.identity.infrastructure.models import User
            from sqlalchemy import select

            user = await uow.session.scalar(select(User).where(User.id == user_id))
            if user is None:
                raise ValueError("Account missing")
            replacement, ttl = await sessions.rotate(
                tenant, sid, secret, cfg.access_token_seconds
            )
            set_refresh_cookie(response, replacement, ttl)
            return LoginResponse(
                access_token=Tokens(cfg).issue(principal, sid),
                expires_in=min(ttl, cfg.access_token_seconds),
                user=UserResponse(
                    user_id=user.id,
                    tenant_id=tenant,
                    email=user.email,
                    display_name=user.display_name,
                    permissions=sorted(principal.permissions),
                ),
            )
    except (ValueError, TypeError) as exc:
        raise HTTPException(401, "Sessão expirada ou revogada.") from exc
    except RedisError as exc:
        raise HTTPException(503, "Serviço de sessão indisponível.") from exc
