from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


class LoginRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    # String at HTTP boundary: explicit UUID parsing, no broad coercion of strict input.
    tenant_id: str = Field(min_length=36, max_length=36)
    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("tenant_id")
    @classmethod
    def tenant_uuid(cls, value: str) -> str:
        return str(UUID(value))

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().casefold() if isinstance(value, str) else value


class UserResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    user_id: UUID
    tenant_id: UUID
    email: str
    display_name: str
    permissions: list[str]


class LoginResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
