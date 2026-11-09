"""Method teaching: when brain.py's deterministic stage planner
(plan_stages, STAGE_REGISTRY) doesn't recognize what an ask needs, ask a
bounded checkpoint to NAME which deterministic primitives to run -- never
to produce content itself.

This is the project owner's own framing: the LLM only fills the reasoning
GAP a deterministic layer doesn't know how to cross -- it teaches the
layer what to do, in a short, controlled way -- and then hands the actual
work back to that layer. The LLM never does the main work. If the layer,
even following the LLM's taught method, still produces nothing or the
LLM's own output doesn't name a real method, that is detected and
discarded right there, not passed through as a guess.

Mechanically: the LLM's entire output is constrained to a closed set of
primitive NAMES (PRIMITIVE_REGISTRY) via Ollama's JSON-schema enum-
constrained decoding -- the same decoding-level constraint
lab.common.real_rewriter_ollama.generate_constrained already uses for a
different field. It is structurally impossible for the model to emit a
name outside this registry, so it is structurally impossible for it to
state a fact: a primitive NAME is the only thing it can produce, and
every primitive is exactly the same deterministic, already-grounded
extraction brain.py trusts elsewhere (entities.detect_primary,
textutil.sentences, calc.parse_date). The LLM composes; the deterministic
layer still does every single extraction.

A malformed/empty plan, or a plan that names something outside the
registry, is discarded outright -- never partially run, never "corrected"
by guessing what was probably meant. A plan that runs cleanly but finds
nothing in the real passages is an honest empty result, not a failure to
paper over.
"""

from __future__ import annotations

from datetime import datetime

import requests

from lab.common.calc import parse_date
from lab.common.entities import detect_primary
from lab.common.intent_signals import _best_similarity
from lab.common.textutil import sentences

OLLAMA_URL = "http://localhost:11434/api/generate"
TEACHING_CHECKPOINT = "gemma3:270m"


def _by_label(passages: list[dict], label: str) -> list[dict]:
    rows = []
    for p in passages:
        text = p.get("text", "") or ""
        for m in detect_primary(text):
            if m["label"] == label:
                rows.append({"passage_id": p["id"], "span": m["text"], "start": m["start"], "end": m["end"]})
    return rows


def _extract_dates(passages: list[dict], prior: list[dict] | None = None) -> list[dict]:
    # `prior` is folded in (not discarded) so chaining two `extract_*`
    # primitives in one plan accumulates both kinds of finding instead of
    # the second step silently overwriting the first's -- a real bug the
    # first live test of this module caught (a 4-step all-"extract_*" plan
    # degenerated to only its last step's output).
    return (prior or []) + _by_label(passages, "date")


def _extract_persons(passages: list[dict], prior: list[dict] | None = None) -> list[dict]:
    return (prior or []) + _by_label(passages, "person")


def _extract_organizations(passages: list[dict], prior: list[dict] | None = None) -> list[dict]:
    return (prior or []) + _by_label(passages, "organization")


def _extract_amounts(passages: list[dict], prior: list[dict] | None = None) -> list[dict]:
    return (prior or []) + _by_label(passages, "amount")


def _group_by_sentence(passages: list[dict], prior: list[dict] | None) -> list[dict]:
    """Attaches, to each item `_extract_*` found, the sentence
    (lab.common.textutil.sentences) it actually occurs in -- a deterministic
    lookup, not a guess: the item's own `span` must literally appear in the
    candidate sentence for it to be kept.
    """
    by_id = {p["id"]: p.get("text", "") or "" for p in passages}
    rows = []
    for item in prior or []:
        text = by_id.get(item.get("passage_id"), "")
        for sent in sentences(text):
            if item.get("span", "") in sent:
                rows.append({**item, "sentence": sent})
                break
    return rows


def _sort_chronological(passages: list[dict], prior: list[dict] | None) -> list[dict]:
    """Sorts prior items by each item's own `span` parsed as a date
    (lab.common.calc.parse_date, the same parser lab.common.temporal
    already relies on) -- an item whose span doesn't parse as a date sorts
    last, never dropped silently.
    """

    def key(row: dict):
        parsed = parse_date(row.get("span", ""))
        return parsed or datetime.max

    return sorted(prior or [], key=key)


def _count(passages: list[dict], prior: list[dict] | None) -> dict:
    return {"count": len(prior or [])}


PRIMITIVE_REGISTRY = {
    "extract_dates": _extract_dates,
    "extract_persons": _extract_persons,
    "extract_organizations": _extract_organizations,
    "extract_amounts": _extract_amounts,
    "group_by_sentence": _group_by_sentence,
    "sort_chronological": _sort_chronological,
    "count": _count,
}

_PRIMITIVE_BLURBS = {
    "extract_dates": "finds every date mentioned in the passages",
    "extract_persons": "finds every person's name mentioned",
    "extract_organizations": "finds every organization name mentioned",
    "extract_amounts": "finds every amount/number-with-unit mentioned",
    "group_by_sentence": "attaches the sentence each prior finding came from",
    "sort_chronological": "sorts prior findings (as dates) earliest first",
    "count": "counts how many prior findings there are",
}

NO_MATCH = "no_matching_tool"

PLAN_PROMPT = """Below is a closed list of tools and a question. Pick which
tools, in order, would answer the question -- you are naming tools only,
never answering the question yourself. If none of these tools, in any
order, could answer the question, reply with exactly one step:
"{no_match}" -- do not force a bad fit.

Tools:
{tool_list}

Question: {ask}"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {"type": "string", "enum": [*PRIMITIVE_REGISTRY, NO_MATCH]},
            "minItems": 1,
            "maxItems": 4,
        }
    },
    "required": ["steps"],
}


def propose_method(ask: str, checkpoint: str = TEACHING_CHECKPOINT, max_tokens: int = 60) -> list[str] | None:
    """Asks the checkpoint to name 1-4 primitives, in order, constrained by
    Ollama's JSON-schema `enum` so a name outside PRIMITIVE_REGISTRY cannot
    be generated at all. Returns `None` (never an empty-but-truthy value)
    for anything that isn't a clean, well-formed plan: bad JSON, a missing
    `steps` key, or a `steps` value that validate_plan rejects.
    """
    tool_list = "\n".join(f"- {name}: {_PRIMITIVE_BLURBS[name]}" for name in PRIMITIVE_REGISTRY)
    prompt = PLAN_PROMPT.format(tool_list=tool_list, ask=ask, no_match=NO_MATCH)
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": checkpoint,
            "prompt": prompt,
            "stream": False,
            "format": _SCHEMA,
            "options": {"num_predict": max_tokens, "temperature": 0, "seed": 0},
        },
        timeout=60,
    )
    resp.raise_for_status()
    import json

    try:
        parsed = json.loads(resp.json()["response"])
    except (json.JSONDecodeError, KeyError):
        return None
    steps = parsed.get("steps")
    return validate_plan(steps)


# Live-tested finding (2026-11-09): asked directly, with an explicit
# "no_matching_tool" escape option offered in the prompt, gemma3:270m still
# defaulted to the generic extract_dates/persons/organizations/amounts plan
# for every one of 3 genuinely out-of-scope asks ("What is the overall tone
# of this case?", "strongest argument", "summarize in one sentence") rather
# than ever choosing the escape option -- the same "always produce SOME
# confident answer" bias lab.common.gapfill already found, now shown at the
# planning level too. A self-reported plan cannot be trusted to mean it
# actually fits; it is cross-checked here instead, the same
# never-trust-the-claim discipline as everywhere else in this module.
#
# lab.common.intent_signals already solves exactly this judgment --
# "does this ask's QUESTION FORM match a capability's form" -- for brain.py's
# own stages (wants_identity/wants_total/...), via bge cosine similarity
# against a few exemplar phrasings per capability, calibrated per-capability.
# Reused here (_best_similarity) rather than reinvented, for the SAME kind of
# judgment applied to this module's own primitives. Note this is a
# different judgment than lab.common.gapfill's embedding pre-filter attempt,
# which failed: that compared an ask against PASSAGE CONTENT to guess
# fact-presence (topical overlap isn't presence-of-fact); this compares an
# ask against CAPABILITY-DESCRIPTION exemplars to guess question-form fit --
# the same comparison intent_signals.py already relies on successfully.
_INTENT_EXEMPLARS = {
    "extract_dates": ("When did this happen?", "What dates are mentioned?", "Give me a timeline of events."),
    "extract_persons": ("Who is named in this case?", "What are the names of the people involved?"),
    "extract_organizations": ("What organizations are mentioned?", "Which companies are named?"),
    "extract_amounts": ("How much money is involved?", "What amounts are mentioned?"),
    "count": ("How many are there?", "What is the count?"),
}
# A first measured value from one live test batch (timeline/list-orgs/
# how-many-people scored 0.726-0.954; three genuinely out-of-scope asks
# scored 0.582-0.626) -- a real gap, same shape as intent_signals.py's own
# calibration note, but NOT yet calibrated the way IDENTITY_TAU/TOTAL_TAU
# were (against a dedicated cross-domain exploration). Treat as provisional
# until that exists.
INTENT_TAU = 0.75


def plan_matches_intent(ask: str, steps: list[str], tau: float = INTENT_TAU) -> dict:
    """Checks the proposed plan's own content-producing steps (the
    `_INTENT_EXEMPLARS` keys; `group_by_sentence`/`sort_chronological` are
    composition-only and have no standalone intent of their own, so they
    never block or contribute here) against what the ask's question FORM
    actually looks like it wants. The plan passes if ANY of its
    content-producing steps scores at or above `tau` -- a plan can
    legitimately combine one well-matched step with others, so the
    strongest step, not the weakest, decides.
    """
    scored = {name: _best_similarity(ask, _INTENT_EXEMPLARS[name]) for name in steps if name in _INTENT_EXEMPLARS}
    best_score = max(scored.values(), default=0.0)
    return {"fires": best_score >= tau, "scores": {k: round(v, 4) for k, v in scored.items()}, "tau": tau}


def validate_plan(steps) -> list[str] | None:
    """The one gate every proposed plan must pass before anything runs:
    `steps` must be a non-empty list, every entry a real PRIMITIVE_REGISTRY
    name, OR the single sentinel step `NO_MATCH` -- the model's own
    admission that no combination of existing primitives answers this ask,
    which is a VALID, meaningful plan (gap correctly detected), not a
    malformed one. Enum-constrained decoding already makes a name outside
    the registry (and NO_MATCH) unlikely, but this does not trust that -- it
    is checked again here unconditionally, the same "never trust the LLM's
    own claim" discipline lab.common.gapfill applies to spans, applied here
    to plan steps instead.
    """
    if not isinstance(steps, list) or not steps:
        return None
    if steps == [NO_MATCH]:
        return steps
    if not all(isinstance(s, str) and s in PRIMITIVE_REGISTRY for s in steps):
        return None
    return steps


def execute_method(steps: list[str], passages: list[dict]) -> list | dict:
    """Runs each named primitive in order, threading one step's output into
    the next as `prior` -- plain deterministic composition, no judgment
    calls. `steps` must already be `validate_plan`-clean; this does not
    re-check membership, so never call it with raw, unvalidated input.
    """
    result: list | dict = []
    for name in steps:
        result = PRIMITIVE_REGISTRY[name](passages, result)
    return result


def teach_and_execute(ask: str, passages: list[dict], checkpoint: str = TEACHING_CHECKPOINT) -> dict:
    """The one function a caller (brain.reason, eventually) actually uses:
    propose a plan, validate it, execute it, and report plainly whether it
    produced anything. `ok=False` covers both failure shapes the project
    owner asked to be handled identically -- a malformed plan, and a clean
    plan that found nothing real -- so a caller never has to tell them
    apart to decide whether to trust the result.
    """
    steps = propose_method(ask, checkpoint=checkpoint)
    if steps is None:
        return {"ok": False, "steps": None, "result": None, "reason": "invalid_or_missing_plan"}
    if steps == [NO_MATCH]:
        # The model's own correctly-shaped admission that nothing in
        # PRIMITIVE_REGISTRY fits -- a genuine capability GAP, reported as
        # such (distinct from a malformed-output failure), so a caller --
        # or a human reading AUDIT.md later -- can tell "the toolbox needs
        # a new primitive for this ask type" apart from "the model's output
        # didn't parse."
        return {"ok": False, "steps": steps, "result": None, "reason": "no_matching_tool"}
    intent_check = plan_matches_intent(ask, steps)
    if not intent_check["fires"]:
        # The plan named only real primitives, but none of them actually
        # matches what this ask's own question form looks like it wants --
        # the deterministic override for the failure this module's live
        # testing found: the model defaulting to its one favorite generic
        # plan regardless of fit, instead of ever using the NO_MATCH escape
        # it was explicitly offered. Reported the same way an explicit
        # NO_MATCH is, since that is what this plan should have been.
        return {"ok": False, "steps": steps, "result": None, "reason": "no_matching_tool", "intent_check": intent_check}
    try:
        result = execute_method(steps, passages)
    except (TypeError, AttributeError, KeyError):
        # A structurally valid plan (every name real) can still be a
        # nonsensical SEQUENCE -- e.g. "count" (produces a dict) feeding
        # into "extract_persons" (expects a list) -- which a membership
        # check alone can't catch. This is exactly the "garbage, detect it,
        # stop right there" case the plan membership check can't see:
        # caught here instead of crashing the caller, reported the same
        # way an invalid plan is, never a partial/garbled result.
        return {"ok": False, "steps": steps, "result": None, "reason": "plan_sequence_invalid"}
    # A non-empty dict is still "nothing found" if its own count is 0 --
    # bool(result) alone would wrongly call {"count": 0} a success, caught
    # by this module's first live test ("list the organizations" picked a
    # wrong-but-structurally-valid plan ending in `count`, over an empty
    # extraction).
    found = bool(result) and result.get("count", 1) != 0 if isinstance(result, dict) else bool(result)
    return {"ok": found, "steps": steps, "result": result, "reason": None if found else "plan_ran_but_found_nothing"}
