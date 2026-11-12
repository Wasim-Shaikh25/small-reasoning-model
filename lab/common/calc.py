"""Date and amount tools. Inputs are extracted spans; the step is shown in the output."""

from __future__ import annotations

import re
from datetime import datetime

import dateparser


def parse_date(text: str) -> datetime | None:
    if not text:
        return None
    return dateparser.parse(text, settings={"STRICT_PARSING": False})


# add_period moved to lab.tests.support on 2026-11-12 -- never called by
# lab.common itself, only exp_007/exp_012's own date-math fixtures.


def compare_numbers(a: str, b: str) -> dict:
    def _num(text: str) -> float | None:
        match = re.search(r"\d[\d,]*(?:\.\d+)?", text or "")
        if not match:
            return None
        return float(match.group(0).replace(",", ""))

    na, nb = _num(a), _num(b)
    if na is None or nb is None:
        return {"ok": False, "error": "unparsed_number", "inputs": [a, b]}
    if na == nb:
        relation = "equal"
    elif na > nb:
        relation = "greater"
    else:
        relation = "less"
    return {
        "ok": True,
        "relation": relation,
        "values": [na, nb],
        "inputs": [a, b],
        "rule": "numeric comparison of extracted spans",
        "provenance": "inference",
    }


def sum_amounts(spans: list[str]) -> dict:
    total = 0.0
    used = []
    for span in spans:
        match = re.search(r"\d[\d,]*(?:\.\d+)?", span or "")
        if not match:
            continue
        value = float(match.group(0).replace(",", ""))
        total += value
        used.append(value)
    return {
        "ok": bool(used),
        "total": total,
        "inputs": used,
        "rule": "sum of extracted amounts",
        "provenance": "inference",
    }
