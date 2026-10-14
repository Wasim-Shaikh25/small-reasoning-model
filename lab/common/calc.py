"""Date and amount tools. Inputs are extracted spans; the step is shown in the output."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

import dateparser


def parse_date(text: str) -> datetime | None:
    if not text:
        return None
    return dateparser.parse(text, settings={"STRICT_PARSING": False})


def add_period(start_text: str, period_text: str) -> dict:
    start = parse_date(start_text)
    if start is None:
        return {"ok": False, "error": "unparsed_date", "inputs": [start_text, period_text]}
    days = re.search(r"(\d+)\s*day", period_text or "", re.I)
    months = re.search(r"(\d+)\s*month", period_text or "", re.I)
    if days:
        end = start + timedelta(days=int(days.group(1)))
        rule = "end = start + N days"
    elif months:
        month = start.month - 1 + int(months.group(1))
        year = start.year + month // 12
        month = month % 12 + 1
        end = start.replace(year=year, month=month)
        rule = "end = start + N calendar months"
    else:
        return {"ok": False, "error": "unparsed_period", "inputs": [start_text, period_text]}
    return {
        "ok": True,
        "result": end.strftime("%d %B %Y"),
        "inputs": {"start": start_text, "period": period_text},
        "rule": rule,
        "provenance": "inference",
    }


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
