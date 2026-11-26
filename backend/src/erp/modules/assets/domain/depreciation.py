from datetime import date
from decimal import Decimal, ROUND_HALF_UP


def depreciation(
    cost: Decimal, residual: Decimal, life_months: int, service_on: date, as_of: date
) -> dict[str, str | int]:
    """Gerencial linear: meses civis completos, início no mês seguinte à ativação."""
    if cost <= 0 or not 0 <= residual <= cost or not 1 <= life_months <= 1200:
        raise ValueError("Parâmetros de depreciação inválidos")
    months = max(
        0,
        min(
            life_months,
            (as_of.year - service_on.year) * 12 + as_of.month - service_on.month,
        ),
    )
    base = cost - residual

    def rounded(value: Decimal) -> str:
        return format(value.quantize(Decimal(".01"), rounding=ROUND_HALF_UP), ".2f")

    accumulated = (base * months / life_months).quantize(
        Decimal(".01"), rounding=ROUND_HALF_UP
    )
    return {
        "months": months,
        "monthly": rounded(base / life_months),
        "accumulated": rounded(accumulated),
        "book_value": rounded(cost - accumulated),
    }
