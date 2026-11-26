from decimal import Decimal, ROUND_HALF_UP

# Educational simulation only: not statutory rates, not a SEFAZ calculation.
RATES = {
    "simples": {"ICMS": "0.03", "PIS": "0.006", "COFINS": "0.02", "ISS": "0.02"},
    "presumido": {"ICMS": "0.12", "PIS": "0.0065", "COFINS": "0.03", "ISS": "0.03"},
    "real": {"ICMS": "0.18", "PIS": "0.0165", "COFINS": "0.076", "ISS": "0.05"},
}
RULE_VERSION = "DEMO-2026-01"


def calculate(base: Decimal, regime: str, kind: str) -> dict[str, dict[str, str]]:
    if base <= 0 or regime not in RATES or kind not in ("nfe", "nfse"):
        raise ValueError("Configuração fiscal inválida")
    names = ("ICMS", "PIS", "COFINS") if kind == "nfe" else ("ISS", "PIS", "COFINS")
    return {
        name: {
            "base": str(base),
            "rate": RATES[regime][name],
            "amount": str(
                (base * Decimal(RATES[regime][name])).quantize(
                    Decimal(".01"), rounding=ROUND_HALF_UP
                )
            ),
        }
        for name in names
    }
