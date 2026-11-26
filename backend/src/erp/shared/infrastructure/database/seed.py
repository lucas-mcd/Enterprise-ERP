from erp.modules.integration.infrastructure.training import create_training
from erp.modules.integration.infrastructure.seed import seed_integration
import erp.modules.integration.infrastructure.models  # noqa: F401
from erp.modules.projects.infrastructure.seed import seed_enterprise
from erp.modules.governance.infrastructure.seed import seed_ecosystem
from erp.modules.operations.infrastructure.seed import seed_operations

"""Run: python -m erp.shared.infrastructure.database.seed --demo.

No production credentials in source. One transaction; stable identities; no
password reset, restore or privilege repair on repeated runs.
"""

import argparse
from erp.modules.financeiro.infrastructure.seed import seed_cash_demo
import asyncio
import getpass
import json
import os
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TypeVar, cast
from uuid import UUID, uuid4, uuid5
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from erp.config import settings
from erp.modules.identity.infrastructure.models import (
    User,
    Role,
    Permission,
    UserRole,
    RolePermission,
)
from erp.modules.identity.infrastructure.passwords import ArgonPasswords
from erp.modules.organization.infrastructure.models import Tenant, DemoActivity
from erp.shared.infrastructure.database.base import Entity
from erp.shared.infrastructure.database.context import AuditContext
from erp.shared.infrastructure.database.session import session_factory

DEFAULT_TENANT = UUID("11111111-1111-4111-8111-111111111111")
PERMISSIONS = (
    "projetos:projeto:ler",
    "projetos:projeto:escrever",
    "projetos:entrega:faturar",
    "ativos:patrimonio:ler",
    "ativos:patrimonio:escrever",
    "identidade:perfil:ler",
    "identidade:dashboard:ler",
    "identidade:usuario:gerenciar",
    "identidade:permissao:gerenciar",
    "auditoria:registro:ler",
    "financeiro:lancamento:ler",
    "financeiro:lancamento:escrever",
    "financeiro:conciliacao:executar",
    "financeiro:relatorio:ler",
    "compras:pedido:ler",
    "compras:pedido:escrever",
    "compras:aprovacao:senior",
    "vendas:pedido:ler",
    "vendas:pedido:escrever",
    "vendas:desconto:aprovar",
    "estoque:saldo:ler",
    "estoque:movimento:escrever",
    "fiscal:documento:ler",
    "fiscal:documento:emitir",
    "rh:folha:ler",
    "rh:folha:processar",
)
COMMON = ("identidade:perfil:ler", "identidade:dashboard:ler")
ROLES: dict[str, tuple[str, ...]] = {
    "Administrador": PERMISSIONS,
    "Financeiro": COMMON
    + (
        "financeiro:lancamento:ler",
        "financeiro:lancamento:escrever",
        "financeiro:conciliacao:executar",
        "financeiro:relatorio:ler",
    ),
    "Vendedor": COMMON
    + ("vendas:pedido:ler", "vendas:pedido:escrever", "estoque:saldo:ler"),
}
USERS = (
    ("admin@enterprise.com", "Administrador", "Administrador", "SEED_ADMIN_PASSWORD"),
    (
        "financeiro@enterprise.com",
        "Marina Costa",
        "Financeiro",
        "SEED_FINANCE_PASSWORD",
    ),
    ("vendedor@enterprise.com", "Rafael Lima", "Vendedor", "SEED_SALES_PASSWORD"),
)
T = TypeVar("T", bound=Entity)


@dataclass(frozen=True)
class SeedOptions:
    tenant_id: UUID = DEFAULT_TENANT
    tenant_name: str = "Enterprise — Empresa Mãe"
    demo: bool = False
    interactive: bool = False
    passwords: dict[str, str] = field(default_factory=dict, repr=False)
    training: bool = False


@dataclass
class SeedReport:
    created: int = 0
    existing: int = 0


async def populate(
    factory: async_sessionmaker[AsyncSession], options: SeedOptions
) -> SeedReport:
    tenant = options.tenant_id
    ctx = AuditContext(
        tenant,
        uuid5(tenant, "seed:service"),
        "bootstrap",
        uuid4(),
        user_agent="enterprise-erp/seed-v2",
    )
    report = SeedReport()
    passwords = ArgonPasswords()
    async with factory(info={"audit_context": ctx}) as session:
        async with session.begin():
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                # A transaction-scoped advisory lock is the only direct SQL path here.
                # It serializes seeds for this tenant; no business DML bypasses ORM.
                connection = await session.connection()
                await connection.execute(
                    select(func.pg_advisory_xact_lock(tenant.int % (2**63)))
                )

            async def ensure(
                model: type[T], identity: UUID, values: dict[str, object]
            ) -> tuple[T, bool]:
                existing = await session.scalar(
                    select(model).where(model.id == identity)
                )
                if existing is not None:
                    report.existing += 1
                    return existing, False
                obj = model(id=identity, tenant_id=tenant, **values)
                session.add(obj)
                await session.flush()
                report.created += 1
                return obj, True

            if options.training and await session.scalar(select(Tenant.id)):
                raise ValueError("O treinamento exige uma empresa nova.")
            await ensure(
                Tenant, tenant, {"name": options.tenant_name, "is_active": True}
            )
            permissions: dict[str, Permission] = {}
            for code in PERMISSIONS:
                obj, _ = await ensure(
                    Permission, uuid5(tenant, f"permission:{code}"), {"code": code}
                )
                if obj.code != code:
                    raise ValueError(
                        "Seed permission identity was modified; review manually"
                    )
                permissions[code] = obj
            roles: dict[str, Role] = {}
            for name, codes in ROLES.items():
                role, _ = await ensure(
                    Role, uuid5(tenant, f"role:{name}"), {"name": name}
                )
                if role.name != name:
                    raise ValueError("Seed role identity was modified; review manually")
                roles[name] = role
                for code in codes:
                    grant, _ = await ensure(
                        RolePermission,
                        uuid5(tenant, f"grant:{name}:{code}"),
                        {"role_id": role.id, "permission_id": permissions[code].id},
                    )
                    if (
                        grant.role_id != role.id
                        or grant.permission_id != permissions[code].id
                    ):
                        raise ValueError("Seed grant was modified; review manually")
            for email, display_name, role_name, env_key in USERS:
                identity = uuid5(tenant, f"user:{email}")
                existing = await session.scalar(select(User).where(User.email == email))
                if existing is not None and existing.id != identity:
                    raise ValueError(
                        f"Email {email} already belongs to a non-seed account"
                    )
                if existing is None:
                    password = options.passwords.get(env_key, "")
                    if not password and options.interactive:
                        password = getpass.getpass(
                            f"Nova senha para {email} (mínimo 14 caracteres): "
                        )
                    if not 14 <= len(password) <= 128:
                        raise ValueError(
                            f"Set {env_key} to a password between 14 and 128 characters"
                        )
                    encoded = await passwords.hash(password)
                    account, _ = await ensure(
                        User,
                        identity,
                        {
                            "email": email,
                            "display_name": display_name,
                            "password_hash": encoded,
                            "is_active": True,
                            "approval_limit": (
                                Decimal("100000")
                                if role_name == "Administrador"
                                else Decimal("0")
                            ),
                        },
                    )
                else:
                    account = existing
                    report.existing += 1
                link, _ = await ensure(
                    UserRole,
                    uuid5(tenant, f"user-role:{email}:{role_name}"),
                    {"user_id": account.id, "role_id": roles[role_name].id},
                )
                if link.user_id != account.id or link.role_id != roles[role_name].id:
                    raise ValueError("Seed membership was modified; review manually")
            if options.demo:
                for i in range(1, 37):
                    code = f"DEMO-{i:03d}"
                    category = "financeiro" if i % 2 else "vendas"
                    record, created = await ensure(
                        DemoActivity,
                        uuid5(tenant, code),
                        {
                            "code": code,
                            "category": category,
                            "description": f"Simulação {category} — operação {i:03d}",
                            "status": "pendente",
                            "amount": Decimal(i * 137 + 250),
                            "is_simulated": True,
                        },
                    )
                    if created and i % 3 == 0:
                        record.status = "concluido"
                        await session.flush()  # Produces a real UPDATE audit record.
            if options.demo:
                new_cash, existing_cash = await seed_cash_demo(session, tenant)
                report.created += new_cash
                report.existing += existing_cash
                new_operations, existing_operations = await seed_operations(
                    session, tenant
                )
                report.created += new_operations
                report.existing += existing_operations
                report.created += await seed_ecosystem(session, tenant)
                report.created += await seed_enterprise(session, tenant)
            report.created += await seed_integration(session, tenant, options.demo)
            if options.training:
                await create_training(session, tenant)
    return report


async def run(options: SeedOptions) -> SeedReport:
    factory = session_factory(settings().database_url)
    try:
        return await populate(factory, options)
    finally:
        await cast(AsyncEngine, factory.kw["bind"]).dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tenant-id",
        type=UUID,
        default=UUID(os.getenv("SEED_TENANT_ID", str(DEFAULT_TENANT))),
    )
    parser.add_argument("--tenant-name", default="Enterprise — Empresa Mãe")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Create 36 demo activities and 36 simulated cash entries",
    )
    parser.add_argument(
        "--training",
        action="store_true",
        help="Create a fresh editable rehearsal tenant",
    )
    args = parser.parse_args()
    if not 1 <= len(args.tenant_name) <= 160:
        parser.error("tenant-name must have 1..160 characters")
    options = SeedOptions(
        uuid4() if args.training else args.tenant_id,
        "Distribuidora Horizonte · Treinamento" if args.training else args.tenant_name,
        args.demo,
        sys.stdin.isatty(),
        {key: os.getenv(key, "") for *_, key in USERS},
        args.training,
    )
    try:
        report = asyncio.run(run(options))
    except IntegrityError:
        parser.exit(
            1,
            "Seed rolled back: identity conflict or soft-deleted seed data. "
            "Review explicitly; no automatic restoration.\n",
        )
    except ValueError as exc:
        parser.exit(1, f"Seed rolled back: {exc}\n")
    print(
        json.dumps(
            {
                "tenant_id": str(options.tenant_id),
                "created": report.created,
                "existing": report.existing,
                "demo": options.demo,
            }
        )
    )


if __name__ == "__main__":
    main()
