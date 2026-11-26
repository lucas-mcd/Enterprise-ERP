from erp.modules.integration.presentation.routers import router as integration_router
import erp.modules.integration.infrastructure.models  # noqa: F401
from erp.modules.projects.presentation.routers import router as projects_router
from erp.modules.assets.presentation.routers import router as assets_router
from erp.modules.cockpit.presentation.routers import router as cockpit_router
from erp.modules.governance.presentation.analytics import router as analytics_router
from erp.modules.governance.presentation.routers import router as governance_router
from erp.modules.fiscal.presentation.routers import router as fiscal_router
from erp.modules.hcm.presentation.routers.workforce import router as hcm_router
from erp.modules.reports.presentation.routers import router as reports_router
from erp.modules.operations.presentation.routers import stock, order_router
from erp.modules.operations.domain.orders import BusinessError
from collections.abc import AsyncIterator
from erp.modules.financeiro.presentation.routers.cash import router as cash_router
from contextlib import asynccontextmanager
from typing import cast
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from erp.modules.identity.presentation.routers.auth import router as auth_router
from erp.modules.identity.presentation.routers.dashboard import (
    router as dashboard_router,
)
from erp.modules.identity.infrastructure.passwords import password_service
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.ext.asyncio import AsyncEngine
from erp.config import settings
from erp.modules.identity.presentation.routers.me import router
from erp.shared.infrastructure.database.session import session_factory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    cfg = settings()
    if len(cfg.jwt_secret.get_secret_value()) < 32:
        raise RuntimeError("JWT_SECRET must contain at least 32 characters")
    password_service()  # Initialize the dummy hash once at startup.
    app.state.sessions = session_factory(cfg.database_url)
    app.state.redis = Redis.from_url(
        cfg.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
    )
    try:
        yield
    finally:
        await app.state.redis.aclose()
        engine = cast(AsyncEngine, app.state.sessions.kw["bind"])
        await engine.dispose()


app = FastAPI(title="Enterprise ERP", version="0.8.0", lifespan=lifespan)
app.include_router(router, prefix="/api/v1")
app.include_router(cash_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")


@app.exception_handler(RequestValidationError)
async def validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": list(e["loc"]), "msg": "Valor inválido.", "type": e["type"]}
                for e in exc.errors()
            ]
        },
    )


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def ready() -> dict[str, str]:
    try:
        engine = cast(AsyncEngine, app.state.sessions.kw["bind"])
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        await app.state.redis.ping()
    except (SQLAlchemyError, RedisError) as exc:
        raise HTTPException(503, "Dependency unavailable") from exc
    return {"status": "ready"}


@app.exception_handler(StaleDataError)
async def conflict(request: Request, exc: StaleDataError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": "Dados alterados em outra sessão. Tente novamente."},
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    return JSONResponse(
        status_code=503, content={"detail": "Serviço de dados indisponível."}
    )


app.include_router(stock, prefix="/api/v1")
app.include_router(order_router("/vendas", "sale", "vendas"), prefix="/api/v1")
app.include_router(order_router("/compras", "purchase", "compras"), prefix="/api/v1")


@app.exception_handler(BusinessError)
async def business_error(request: Request, exc: BusinessError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


app.include_router(reports_router, prefix="/api/v1")


@app.exception_handler(IntegrityError)
async def integrity_conflict(request: Request, exc: IntegrityError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": (
                "Conflito de cadastro ou vínculo. "
                "Atualize os dados e tente novamente."
            )
        },
    )


app.include_router(governance_router, prefix="/api/v1")
app.include_router(fiscal_router, prefix="/api/v1")
app.include_router(hcm_router, prefix="/api/v1")

app.include_router(analytics_router, prefix="/api/v1")


app.include_router(projects_router, prefix="/api/v1")
app.include_router(assets_router, prefix="/api/v1")


app.include_router(cockpit_router, prefix="/api/v1")

app.include_router(integration_router, prefix="/api/v1")
