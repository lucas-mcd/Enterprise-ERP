from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID


class BusinessError(Exception):
    """A workflow precondition failed; the UoW must roll back."""


@dataclass(frozen=True)
class Line:
    product_id: UUID
    quantity: int
    unit_price: Decimal


def total(lines: list[Line]) -> Decimal:
    if not 1 <= len(lines) <= 50 or len({x.product_id for x in lines}) != len(lines):
        raise BusinessError("Use de 1 a 50 produtos distintos.")
    for x in lines:
        if (
            not 1 <= x.quantity <= 100000
            or not x.unit_price.is_finite()
            or not Decimal("0") < x.unit_price <= Decimal("999999999.99")
        ):
            raise BusinessError("Quantidade ou preço inválido.")
        if x.unit_price != x.unit_price.quantize(Decimal(".01")):
            raise BusinessError("Use duas casas decimais.")
    result = sum((x.unit_price * x.quantity for x in lines), Decimal("0"))
    if result > Decimal("999999999.99"):
        raise BusinessError("Total excede o limite financeiro.")
    return result
