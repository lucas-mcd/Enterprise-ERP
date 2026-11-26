"""Generate the public API contract. Run with the backend dependencies installed."""
import json
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend" / "src"))
os.environ.setdefault("JWT_SECRET", "schema-generation-only-no-running-service")
from erp.main import app

target = root / "docs" / "openapi.json"
target.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
