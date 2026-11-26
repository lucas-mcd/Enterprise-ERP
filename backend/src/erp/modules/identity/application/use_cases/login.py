from erp.modules.identity.application.ports.auth import (
    CredentialsReader,
    PasswordService,
)
from erp.modules.identity.domain.auth import AuthenticatedAccount, InvalidCredentials


class Login:
    """Authenticate without depending on HTTP, ORM, JWT or Redis implementations."""

    def __init__(
        self, identities: CredentialsReader, passwords: PasswordService
    ) -> None:
        self.identities = identities
        self.passwords = passwords

    async def execute(self, email: str, password: str) -> AuthenticatedAccount:
        account = await self.identities.account(email)
        valid = await self.passwords.verify(
            password, account.password_hash if account else None
        )
        if not valid or account is None or not account.active:
            raise InvalidCredentials()
        if not await self.identities.tenant_active():
            raise InvalidCredentials()
        principal = await self.identities.principal(account.user_id)
        if principal is None:
            raise InvalidCredentials()
        if self.passwords.needs_rehash(account.password_hash):
            await self.identities.replace_hash(
                account.user_id, await self.passwords.hash(password)
            )
        return AuthenticatedAccount(account, principal)
