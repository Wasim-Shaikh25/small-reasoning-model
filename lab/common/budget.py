"""Controller budgets. Learned components propose; this code disposes."""

from __future__ import annotations

import json
from pathlib import Path

CONFIG = json.loads((Path(__file__).resolve().parents[1] / "config" / "budgets.json").read_text())


def cap_depth(proposed: str, override: str | None = None) -> dict:
    depths = CONFIG["depths"]
    caps = CONFIG["caps"]
    name = override or proposed
    if name not in depths:
        name = "light"
    chosen = depths[name]
    return {
        "depth": name,
        "proposed": proposed,
        "passages_kept": min(chosen["passages_kept"], caps["max_passages_kept"]),
        "max_rounds": min(chosen["max_rounds"], caps["max_rounds"]),
        "capped": name != proposed or chosen["max_rounds"] > caps["max_rounds"],
    }
