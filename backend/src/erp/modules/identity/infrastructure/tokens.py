from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import jwt
from erp.config import Settings
from erp.shared.domain.security import Principal


@dataclass(frozen=True, slots=True)
class TokenIdentity:
    user_id: UUID
    tenant_id: UUID
    session_id: UUID


class Tokens:
    def __init__(self, config: Settings) -> None:
        self.config = config

    def issue(self, principal: Principal, sid: UUID) -> str:
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "sub": str(principal.user_id),
                "tid": str(principal.tenant_id),
                "user_id": str(principal.user_id),
                "tenant_id": str(principal.tenant_id),
                "sid": str(sid),
                "jti": str(uuid4()),
                "typ": "access",
                "iss": self.config.jwt_issuer,
                "aud": self.config.jwt_audience,
                "iat": now,
                "nbf": now,
                "exp": now + timedelta(seconds=self.config.access_token_seconds),
                "permissions": sorted(principal.permissions),
            },
            self.config.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )

    def decode(self, token: str) -> TokenIdentity:
        claims = jwt.decode(
            token,
            self.config.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=self.config.jwt_audience,
            issuer=self.config.jwt_issuer,
            options={"require": ["exp", "iat", "nbf", "sub", "tid", "sid", "jti"]},
        )
        if claims.get("typ") != "access":
            raise ValueError("Access token required")
        user, tenant, sid = (UUID(claims[key]) for key in ("sub", "tid", "sid"))
        if claims.get("user_id", str(user)) != str(user) or claims.get(
            "tenant_id", str(tenant)
        ) != str(tenant):
            raise ValueError("Conflicting identity claims")
        return TokenIdentity(user, tenant, sid)
