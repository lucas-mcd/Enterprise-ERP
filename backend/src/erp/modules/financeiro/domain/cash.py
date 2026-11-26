from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

Kind = Literal["receita", "despesa"]
Status = Literal["pendente", "concluido"]
CATEGORIES = (
    "Vendas",
    "Serviços",
    "Assinaturas",
    "Fornecedores",
    "Pessoal",
    "Marketing",
    "Infraestrutura",
    "Impostos",
    "Outros",
)


class InvalidEntry(ValueError):
    """A cash entry violates a business invariant."""


class IdempotencyConflict(Exception):
    """The same request key was already used with different business data."""


def business_today() -> date:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


@dataclass(frozen=True, slots=True)
class NewEntry:
    description: str
    counterparty: str
    category: str
    kind: Kind
    status: Status
    amount: Decimal
    due_date: date
    settled_on: date | None
    cost_center_id: UUID | None = None

    def validate(self) -> None:
        if not 3 <= len(self.description.strip()) <= 180:
            raise InvalidEntry("A descrição deve ter entre 3 e 180 caracteres.")
        if len(self.counterparty) > 120 or self.category not in CATEGORIES:
            raise InvalidEntry("Categoria ou contraparte inválida.")
        if self.kind not in ("receita", "despesa") or self.status not in (
            "pendente",
            "concluido",
        ):
            raise InvalidEntry("Tipo ou status inválido.")
        if not self.amount.is_finite() or not Decimal("0") < self.amount <= Decimal(
            "999999999.99"
        ):
            raise InvalidEntry("Informe um valor positivo de até 999.999.999,99.")
        if self.amount != self.amount.quantize(Decimal("0.01")):
            raise InvalidEntry("O valor deve ter no máximo duas casas decimais.")
        if not date(2000, 1, 1) <= self.due_date <= date(2100, 12, 31):
            raise InvalidEntry("Vencimento fora do intervalo permitido.")
        if self.status == "pendente" and self.settled_on is not None:
            raise InvalidEntry("Um lançamento pendente não possui data de liquidação.")
        if self.status == "concluido" and (
            self.settled_on is None
            or not date(2000, 1, 1) <= self.settled_on <= business_today()
        ):
            raise InvalidEntry("Informe uma data de liquidação válida, não futura.")


@dataclass(frozen=True)
class EntryView:
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


@dataclass(frozen=True)
class EntryFilter:
    start: date
    end: date
    source: Literal["real", "demo"] = "real"
    status: str | None = None
    kind: str | None = None
    query: str = ""
    category: str | None = None
    sort: str = "effective_on"
    desc: bool = True

    def validate(self) -> None:
        if not date(2000, 1, 1) <= self.start <= self.end <= date(2100, 12, 31):
            raise InvalidEntry("Período fora do intervalo permitido (2000–2100).")
        if (self.end - self.start).days > 365:
            raise InvalidEntry(
                "Selecione um intervalo de até 366 dias, em ordem crescente."
            )
        if self.sort not in (
            "effective_on",
            "amount",
            "description",
            "category",
            "status",
        ):
            raise InvalidEntry("Ordenação inválida.")
        if self.source not in ("real", "demo"):
            raise InvalidEntry("Origem inválida.")
        if self.status not in (
            None,
            "pendente",
            "concluido",
            "aguardando_aprovacao",
        ) or self.kind not in (
            None,
            "receita",
            "despesa",
        ):
            raise InvalidEntry("Filtro inválido.")
        if len(self.query) > 100 or self.category not in (None, *CATEGORIES):
            raise InvalidEntry("Filtro inválido.")


@dataclass(frozen=True)
class EntryPage:
    items: list[EntryView]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class CashPoint:
    day: date
    income: str
    expense: str
    pending_income: str
    pending_expense: str


@dataclass(frozen=True)
class CategoryTotal:
    category: str
    amount: str


@dataclass(frozen=True)
class CashSummary:
    source: str
    total_records: int
    income: str
    expense: str
    net: str
    pending_income: str
    pending_expense: str
    points: list[CashPoint]
    expense_categories: list[CategoryTotal]
