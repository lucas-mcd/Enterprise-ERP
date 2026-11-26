import re
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field, EmailStr, field_validator
from erp.modules.financeiro.presentation.schemas.cash import StrictModel
from erp.modules.financeiro.domain.cash import business_today


def document_number(value: str) -> str:
    value = re.sub(r"[./\-\s]", "", value)
    if (
        not value.isascii()
        or not value.isdigit()
        or len(set(value)) == 1
        or len(value) not in (11, 14)
    ):
        raise ValueError("CPF/CNPJ numérico inválido.")
    digits = [int(x) for x in value]
    weights = (
        list(range(10, 1, -1))
        if len(value) == 11
        else [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    )
    base = digits[:-2]
    for factors in (weights, [weights[0] + 1, *weights]):
        remainder = sum(x * y for x, y in zip(base, factors)) % 11
        base.append(0 if remainder < 2 else 11 - remainder)
    if base != digits:
        raise ValueError("Dígitos verificadores inválidos.")
    return value


class CustomerInput(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    document: str = Field(max_length=30)
    segment: str = Field(min_length=1, max_length=80)
    email: EmailStr
    phone: str = Field(default="", max_length=30)
    credit_limit: str = Field(pattern=r"^\d{1,9}(\.\d{1,2})?$")

    @field_validator("document")
    @classmethod
    def valid_document(cls, value: str) -> str:
        return document_number(value)


class ItemInput(StrictModel):
    product_id: str
    quantity: int = Field(ge=1, le=100000)
    unit_price: str = Field(pattern=r"^\d{1,9}(\.\d{1,2})?$")

    @field_validator("product_id")
    @classmethod
    def uuid_value(cls, value: str) -> str:
        return str(UUID(value))

    @field_validator("unit_price")
    @classmethod
    def positive(cls, value: str) -> str:
        if Decimal(value) <= 0:
            raise ValueError("Preço deve ser positivo.")
        return value


class OpportunityInput(StrictModel):
    title: str = Field(min_length=2, max_length=140)
    customer_id: str
    expected_on: str
    items: list[ItemInput] = Field(min_length=1, max_length=50)

    @field_validator("customer_id")
    @classmethod
    def uuid_value(cls, value: str) -> str:
        return str(UUID(value))

    @field_validator("expected_on")
    @classmethod
    def valid_date(cls, value: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Use YYYY-MM-DD.")
        return date.fromisoformat(value).isoformat()


class VersionInput(StrictModel):
    version: int = Field(ge=1)


class RevisionInput(VersionInput):
    expected_on: str | None = None
    loss_reason: str | None = Field(default=None, min_length=3, max_length=180)


class StageInput(VersionInput):
    stage: Literal["prospeccao", "proposta", "negociacao"]


class StatementLine(StrictModel):
    external_id: str = Field(min_length=1, max_length=120)
    posted_on: str
    description: str = Field(min_length=1, max_length=180)
    amount: str = Field(pattern=r"^-?\d{1,9}(\.\d{1,2})?$")

    @field_validator("posted_on")
    @classmethod
    def date_value(cls, value: str) -> str:
        if (
            not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
            or not date(2000, 1, 1) <= date.fromisoformat(value) <= business_today()
        ):
            raise ValueError("Data inválida ou futura.")
        return value

    @field_validator("amount")
    @classmethod
    def nonzero(cls, value: str) -> str:
        if Decimal(value) == 0:
            raise ValueError("Valor deve ser diferente de zero.")
        return value


class StatementInput(StrictModel):
    account: str = Field(min_length=1, max_length=80)
    reference: str = Field(min_length=1, max_length=80)
    entries: list[StatementLine] = Field(min_length=1, max_length=500)


class SimulateInput(StrictModel):
    reference: str = Field(min_length=1, max_length=80)


class MatchInput(StrictModel):
    cash_entry_id: str

    @field_validator("cash_entry_id")
    @classmethod
    def uuid_value(cls, value: str) -> str:
        return str(UUID(value))
