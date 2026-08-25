"""Load structured persona scripts for simulation rooms."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=8)
def load_p1_supplier_script() -> list[dict]:
    path = _SCRIPTS_DIR / 'p1_supplier.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    return data['turns']


def p1_supplier_offer_rows() -> list[tuple[float, int]]:
    return [(turn['price'], turn['quantity']) for turn in load_p1_supplier_script()]
