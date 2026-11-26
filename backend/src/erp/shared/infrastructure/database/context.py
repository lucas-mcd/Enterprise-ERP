from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuditContext:
    tenant_id: UUID
    actor_id: UUID | None
    actor_kind: str  # user | service | bootstrap; enforced by callers.
    request_id: UUID
    ip: str | None = None
    user_agent: str | None = None
