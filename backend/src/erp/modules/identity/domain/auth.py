from dataclasses import dataclass
from uuid import UUID
from erp.shared.domain.security import Principal


class InvalidCredentials(Exception):
    """Deliberately hides whether a tenant or user exists."""


@dataclass(frozen=True, slots=True)
class Account:
    user_id: UUID
    email: str
    display_name: str
    password_hash: str
    active: bool


@dataclass(frozen=True, slots=True)
class AuthenticatedAccount:
    account: Account
    principal: Principal
