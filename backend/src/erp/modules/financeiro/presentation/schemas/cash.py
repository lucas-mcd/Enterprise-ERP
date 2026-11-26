import re
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from erp.modules.financeiro.domain.cash import NewEntry


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", from_attributes=True)


class CreateEntry(StrictModel):
    description: str = Field(min_length=3, max_length=180)
    counterparty: str = Field(default="", max_length=120)
    category: str = Field(min_length=1, max_length=40)
    kind: Literal["receita", "despesa"]
    status: Literal["pendente", "concluido"] = "pendente"
    amount: str = Field(max_length=12)
    due_date: str
    settled_on: str | None = None
    cost_center_id: str | None = None

    @field_validator("cost_center_id")
    @classmethod
    def center_uuid(cls, value: str | None) -> str | None:
        return str(UUID(value)) if value is not None else None

    @field_validator("description", "counterparty", "category")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("amount")
    @classmethod
    def decimal_string(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,2})?", value):
            raise ValueError("Use decimal positivo com no máximo duas casas.")
        return format(Decimal(value), ".2f")

    @field_validator("due_date", "settled_on")
    @classmethod
    def iso_date(cls, value: str | None) -> str | None:
        if value is not None:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("Use YYYY-MM-DD.")
            return date.fromisoformat(value).isoformat()
        return None

    def command(self) -> NewEntry:
        return NewEntry(
            self.description,
            self.counterparty,
            self.category,
            self.kind,
            self.status,
            Decimal(self.amount),
            date.fromisoformat(self.due_date),
            date.fromisoformat(self.settled_on) if self.settled_on else None,
            UUID(self.cost_center_id) if self.cost_center_id else None,
        )


class EntryResponse(StrictModel):
    id: UUID
    description: str
    counterparty: str
    category: str
    kind: str
    status: str
    amount: str
    currency: str
    due_date: date
    settled_on: date | None
    effective_on: date
    is_simulated: bool
    version: int
    cost_center_id: UUID | None = None


class PageResponse(StrictModel):
    items: list[EntryResponse]
    total: int
    page: int
    page_size: int


class PointResponse(StrictModel):
    day: date
    income: str
    expense: str
    pending_income: str
    pending_expense: str


class CategoryResponse(StrictModel):
    category: str
    amount: str


class SummaryResponse(StrictModel):
    source: str
    total_records: int
    income: str
    expense: str
    net: str
    pending_income: str
    pending_expense: str
    points: list[PointResponse]
    expense_categories: list[CategoryResponse]
