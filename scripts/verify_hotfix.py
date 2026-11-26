"""Verify delivered frontend hashes and mandatory fixes. Run from any directory."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[1]
hashes = json.loads((root / "SOURCE_SHA256.json").read_text())
for relative, expected in hashes.items():
    actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"Arquivo divergente: {relative}")
checks = {
    "shared/lib/format.ts": ["export function safeFormatDate", "Number.isNaN(date.getTime())"],
    "shared/components/ErrorBoundary.tsx": ["componentDidCatch", "getDerivedStateFromError", "resetErrorBoundary"],
    "modules/financeiro/components/CashCharts.tsx": ["safeFormatDate(props.label)", "Sem dados no período"],
    "modules/identity/pages/DashboardPage.tsx": ["LockKeyhole,", "<ErrorBoundary"],
}
for relative, required in checks.items():
    text = (root / "frontend/src" / relative).read_text()
    for token in required:
        if token not in text:
            raise SystemExit(f"Correção ausente: {relative}: {token}")
print("ERP 0.8.0: integridade dos arquivos e proteções de interface confirmadas.")
