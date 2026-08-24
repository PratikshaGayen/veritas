"""Fixture-loading helper for phase 2 tests. Not collected by pytest (no
test_ prefix).
"""

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))
