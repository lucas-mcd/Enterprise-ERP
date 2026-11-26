from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID


class Forbidden(Exception):
    """The principal does not satisfy the complete policy."""


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    tenant_id: UUID
    permissions: frozenset[str]
    company_ids: frozenset[UUID] = frozenset()
    approval_limit: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class ResourceAttributes:
    tenant_id: UUID
    company_id: UUID
    amount: Decimal
    requester_id: UUID


def authorize(
    principal: Principal, action: str, resource: ResourceAttributes | None = None
) -> None:
    """Deny by default. Exact actions; no wildcard or role-name shortcuts."""
    if action not in principal.permissions:
        raise Forbidden(action)
    if resource is not None and (
        resource.tenant_id != principal.tenant_id
        or resource.company_id not in principal.company_ids
        or resource.amount > principal.approval_limit
        or resource.requester_id == principal.user_id
    ):
        raise Forbidden("ABAC: company, amount or segregation of duties")
