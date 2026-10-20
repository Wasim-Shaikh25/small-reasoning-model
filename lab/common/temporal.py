"""Temporal bound reasoning (until/before/after/once) -- EXP-097.

Named, upfront limit this project already stated (lab.common.connectives'
own docstring): TEMPORAL_BOUND connectives are about WHEN, not WHETHER.
check_exception/check_exceptions answer a TRUTH question (does context
affirm or contradict a proposition) -- the wrong tool for an ORDERING
question (has a bounding point in time been reached yet). This module
adds a second, genuinely different reasoning primitive for that
different kind of question, rather than forcing it through the
exception mechanism.

Two paths, tried in order, never conflated:
  1. Absolute: the governing clause names a literal date/duration
     ("until 1 January 2025") -- lab.common.calc.parse_date (already
     used for EXP-007/014's arithmetic) resolves it deterministically
     against a reference point. No NLI, no ambiguity, no "unknown"
     possible here -- a parsed date is simply before or after the
     reference date.
  2. Event-relative: the governing clause names an EVENT, not a date
     ("until the consent is withdrawn") -- whether that event has
     occurred is checked the same bounded way check_exception already
     checks any other clause's truth (one NLI judgment: does given
     context affirm or contradict it). This is the ONLY place this
     module reuses check_exception, and only as a sub-judgment ("has
     this event happened"), never to answer the WHEN question itself.

Direction matters and is not interchangeable (EXP-090's own docstring):
"until"/"before" mean the main clause holds BEFORE the bound and stops
once it's reached; "after"/"once" mean the OPPOSITE -- the main clause
does not hold until the bound is reached, then it does. Two connectives
in the same TEMPORAL_BOUND operator class can require OPPOSITE
validity logic, the same lesson EXP-026 already learned for
CONDITION_NEGATIVE vs CONDITION_POSITIVE.

Status values are deliberately NOT holds/not_holds/unknown (those
answer "is a proposition true"); temporal validity answers "does the
main clause currently apply": "in_effect", "not_in_effect", "unknown"
-- same honest-abstention posture as everywhere else in this repo.
"""

from __future__ import annotations

from datetime import datetime

from lab.common.calc import parse_date
from lab.common.connectives import Operator, find_connectives
from lab.common.inference import check_exception

_VALID_BEFORE = {"until", "before"}
_VALID_AFTER = {"after", "once"}


def find_temporal_bound(consequence: str) -> dict | None:
    """The one TEMPORAL_BOUND connective in `consequence`, if any, split
    into the main clause and the bound clause at the connective's own
    anchor position -- the same single-point split split_exception uses
    for CONDITION_NEGATIVE/POSITIVE, just for a structurally different
    operator class.
    """
    matches = [m for m in find_connectives(consequence) if m.operator == Operator.TEMPORAL_BOUND]
    if not matches:
        return None
    match = matches[0]
    idx = consequence.lower().find(match.anchor_text.lower())
    if idx == -1:
        return None
    main_clause = consequence[:idx].strip().rstrip(",")
    bound_clause = consequence[idx + len(match.anchor_text) :].strip().rstrip(".")
    direction = "valid_before" if match.phrase in _VALID_BEFORE else "valid_after"
    return {"main_clause": main_clause, "bound_clause": bound_clause, "direction": direction, "phrase": match.phrase}


def _resolve_validity(direction: str, bound_reached: bool) -> str:
    if direction == "valid_before":
        return "not_in_effect" if bound_reached else "in_effect"
    return "in_effect" if bound_reached else "not_in_effect"


def check_temporal_bound(bound_clause: str, context_texts: list[str], direction: str, reference_date: datetime | None = None, tau: float = 0.75) -> dict:
    """Does the main clause currently apply, given this temporal bound.
    Tries absolute-date resolution first (deterministic, no NLI, no
    "unknown" possible); falls back to the event-relative NLI check
    only when the bound clause doesn't parse as a literal date at all.
    """
    reference_date = reference_date or datetime.now()
    absolute_date = parse_date(bound_clause)
    if absolute_date is not None:
        bound_reached = reference_date >= absolute_date
        return {
            "status": _resolve_validity(direction, bound_reached),
            "method": "absolute_date",
            "resolved_date": absolute_date.isoformat(),
            "reference_date": reference_date.isoformat(),
        }

    event_result = check_exception(bound_clause, context_texts, tau=tau)
    if event_result["status"] == "holds":
        status = _resolve_validity(direction, bound_reached=True)
    elif event_result["status"] == "not_holds":
        status = _resolve_validity(direction, bound_reached=False)
    else:
        status = "unknown"
    return {"status": status, "method": "event_relative", "event_check": event_result}
