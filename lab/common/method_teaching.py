"""SUPERSEDED for the vocabulary-mapping role (2026-11-10) -- read this
before promoting or extending this module. `_NOUN_TO_LABEL`/
`_WH_TO_LABEL`/`_INTENT_TO_PLAN`/`_INTENT_EXEMPLARS` below are exactly
the hardcoded "ask word -> primitive sequence" pattern
`lab.common.concept_tools` was built to eliminate: a NEW task-vocabulary
entry here still requires a Python change, the thing a YAML-defined
concept in `lab/common/concepts/` no longer does. That replacement is
now proven (AUDIT.md, "the teach-tool concept registry" / "making the
teach-tool layer actually industry-blank"), not just proposed, so this
module should NOT be promoted to the live pipeline as-is -- it is a
candidate for deletion once everything it still does (the bounded-
checkpoint fallback described below) is confirmed to have no caller left
depending on it, per this project's own "promote/delete once the
replacement is measured" rule. Left unmodified rather than half-fixed:
genericizing its tables in place would just produce a second, parallel
version of what `concept_tools.py` already does correctly.

Method teaching: when brain.py's deterministic stage planner
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
from lab.common.rules import _parser, apply_rule, extract_fact_triple, parse_conditional_rule
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


def _list_grounded_arguments(passages: list[dict], prior=None) -> list[dict]:
    """Every (rule, fact) pair among `passages` where the rule's trigger
    verb lemma actually matches the fact's verb lemma
    (lab.common.rules.parse_conditional_rule / extract_fact_triple /
    apply_rule -- the project's own existing natural-language-to-logic
    parser and rule engine, not new code). "Strong" here means exactly
    "grounded, actually fires" -- a rule that parses but matches no fact,
    or a fact that matches no rule, never produces an argument at all.
    This deliberately enumerates EVERY matching pair across every rule in
    `passages`, not just one -- brain.py's own rule_application stage picks
    a single rule via plan_stages for a specific ask; this is the "list
    every side's valid argument" operation the project owner asked for
    instead, built from the same two functions, no new scoring or ranking.
    """
    rules, facts = [], []
    for p in passages:
        text = p.get("text", "") or ""
        rule = parse_conditional_rule(text)
        if rule:
            rules.append({**rule, "passage_id": p["id"]})
            continue
        fact = extract_fact_triple(text)
        if fact and fact.get("verb_lemma"):
            facts.append({**fact, "passage_id": p["id"]})
    arguments = []
    for rule in rules:
        for fact in facts:
            applied = apply_rule(rule, fact)
            if applied["matched"]:
                arguments.append(
                    {
                        "rule_passage": rule["passage_id"],
                        "fact_passage": fact["passage_id"],
                        "rule_text": rule["raw"],
                        "fact_text": fact["raw"],
                        "consequence": applied["consequence"],
                    }
                )
    return arguments


PRIMITIVE_REGISTRY = {
    "extract_dates": _extract_dates,
    "extract_persons": _extract_persons,
    "extract_organizations": _extract_organizations,
    "extract_amounts": _extract_amounts,
    "group_by_sentence": _group_by_sentence,
    "sort_chronological": _sort_chronological,
    "count": _count,
    "list_grounded_arguments": _list_grounded_arguments,
}

_PRIMITIVE_BLURBS = {
    "extract_dates": "finds every date mentioned in the passages",
    "extract_persons": "finds every person's name mentioned",
    "extract_organizations": "finds every organization name mentioned",
    "extract_amounts": "finds every amount/number-with-unit mentioned",
    "group_by_sentence": "attaches the sentence each prior finding came from",
    "sort_chronological": "sorts prior findings (as dates) earliest first",
    "count": "counts how many prior findings there are",
    "list_grounded_arguments": "finds every rule that actually applies to a fact, for any side",
}

NO_MATCH = "no_matching_tool"

# Project owner's own framing, tested directly: the ask itself can become
# logic -- parsed the same structural way lab.common.rules already parses
# rule/fact sentences ("if X, Y" -> trigger/consequence), not matched
# against a model's self-report or a bge-similarity threshold. A WH-word
# (when/who/where) or "how many"/"how much" names an OPERATION directly;
# otherwise the ask's own head noun (its ROOT's object, or subject of a
# copula/ccomp/relcl chain -- the same dependency-parse technique rules.py
# uses for `_main_verb`) names it via a small, FIXED, domain-agnostic
# lemma table -- not growing per ask type, the same way DATE_RE/AMOUNT_RE's
# own label set is fixed. Live-tested across 9 asks (6 in-scope, 3
# deliberately out-of-scope): every one matched correctly, including
# "how many people" correctly landing on `count` for the first time (the
# LLM-proposed plan never once ended in `count` for that ask across every
# earlier test in this module) -- and every out-of-scope ask correctly
# returned `None`, with zero calls to the checkpoint or to bge_embed.
_NOUN_TO_LABEL = {
    "date": "date", "dates": "date", "timeline": "date", "time": "date",
    "person": "person", "people": "person", "name": "person", "names": "person",
    "organization": "organization", "organizations": "organization",
    "company": "organization", "companies": "organization",
    "amount": "amount", "amounts": "amount", "money": "amount", "sum": "amount",
    "argument": "reasoning", "arguments": "reasoning", "rule": "reasoning",
    "rules": "reasoning", "claim": "reasoning",
}
_WH_TO_LABEL = {"when": "date", "who": "person", "where": "address"}

# operation+label -> the concrete plan that answers it. "date" under
# "extract" chains group_by_sentence + sort_chronological too -- a bare
# list of date spans with no context or order isn't actually a timeline;
# every other label stays a plain extraction (no ask ever implied an order
# or grouping for persons/organizations/amounts the way "timeline" does
# for dates).
_INTENT_TO_PLAN = {
    ("extract", "date"): ["extract_dates", "group_by_sentence", "sort_chronological"],
    ("extract", "person"): ["extract_persons"],
    ("extract", "organization"): ["extract_organizations"],
    ("extract", "amount"): ["extract_amounts"],
    ("count", "date"): ["extract_dates", "count"],
    ("count", "person"): ["extract_persons", "count"],
    ("count", "organization"): ["extract_organizations", "count"],
    ("count", "amount"): ["extract_amounts", "count"],
    ("apply_and_chain", "reasoning"): ["list_grounded_arguments"],
}


def parse_ask_intent(ask: str) -> dict | None:
    """Parses `ask` itself into `{"operation", "label"}`, deterministically,
    via dependency parse + a small fixed lemma table -- no checkpoint call,
    no embedding similarity. Returns `None` when neither a WH-word nor the
    ask's own head noun matches anything in the table: an honest "this
    ask's form isn't one the registry's vocabulary covers," not a guess.
    """
    doc = _parser()(ask)
    for token in doc:
        lemma = token.lemma_.lower()
        if lemma in _WH_TO_LABEL:
            return {"operation": "extract", "label": _WH_TO_LABEL[lemma]}
    lowered = ask.lower()
    if "how many" in lowered or "how much" in lowered:
        for token in doc:
            if token.lemma_.lower() in _NOUN_TO_LABEL:
                return {"operation": "count", "label": _NOUN_TO_LABEL[token.lemma_.lower()]}
        return None
    for token in doc:
        if token.dep_ in ("dobj", "nsubj", "nsubjpass", "attr", "pobj") and token.lemma_.lower() in _NOUN_TO_LABEL:
            label = _NOUN_TO_LABEL[token.lemma_.lower()]
            return {"operation": "apply_and_chain" if label == "reasoning" else "extract", "label": label}
    return None


def plan_for_ask(ask: str) -> list[str] | None:
    """The one function `teach_and_execute` tries FIRST, before ever
    calling the checkpoint: `parse_ask_intent` plus `_INTENT_TO_PLAN`'s
    fixed operation+label -> primitive-sequence lookup. `None` means this
    ask's form isn't covered by the table at all -- `teach_and_execute`
    falls back to the checkpoint-proposed path (propose_method +
    plan_matches_intent) only in that case, never as the first attempt.
    """
    intent = parse_ask_intent(ask)
    if intent is None:
        return None
    return _INTENT_TO_PLAN.get((intent["operation"], intent["label"]))


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
    "list_grounded_arguments": (
        "What arguments could each side make?",
        "What rules apply to the facts of this case?",
        "What are the strong arguments here?",
    ),
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


def _run_plan(steps: list[str], passages: list[dict], source: str) -> dict:
    """The execution + containment logic shared by both of
    `teach_and_execute`'s paths (the deterministic ask-parse plan, and the
    checkpoint-proposed one) -- a plan from `plan_for_ask` is already known
    well-formed (built straight from `_INTENT_TO_PLAN`, never from
    unvalidated model output), but still goes through the exact same
    sequence-crash guard and empty/zero-count check as a checkpoint plan,
    on the same "never trust a source, even a deterministic one, to mean
    its own output is safe to run unchecked" discipline as the rest of
    this module. `source` ("ask_parsed" or "checkpoint_proposed") is
    carried into the result so a caller -- or AUDIT.md later -- can always
    tell which path actually produced an answer.
    """
    try:
        result = execute_method(steps, passages)
    except (TypeError, AttributeError, KeyError):
        return {"ok": False, "steps": steps, "result": None, "reason": "plan_sequence_invalid", "source": source}
    found = bool(result) and result.get("count", 1) != 0 if isinstance(result, dict) else bool(result)
    return {
        "ok": found,
        "steps": steps,
        "result": result,
        "reason": None if found else "plan_ran_but_found_nothing",
        "source": source,
    }


def teach_and_execute(ask: str, passages: list[dict], checkpoint: str = TEACHING_CHECKPOINT) -> dict:
    """The one function a caller (brain.reason, eventually) actually uses.
    Tries `plan_for_ask` (the ask parsed into logic, deterministic, no
    checkpoint call) FIRST -- live-tested as strictly more reliable than
    the checkpoint-proposed path below it (9/9 correct vs. the
    checkpoint's repeated wrong/defaulted picks). Falls back to asking the
    checkpoint to propose a plan only when the ask's own form isn't
    covered by `_INTENT_TO_PLAN` at all. Either way, `ok=False` covers
    every failure shape the project owner asked to be handled identically
    -- an ask form nothing recognizes, a malformed checkpoint plan, and a
    clean plan that found nothing real -- so a caller never has to tell
    them apart to decide whether to trust the result.
    """
    steps = plan_for_ask(ask)
    if steps is not None:
        return _run_plan(steps, passages, source="ask_parsed")
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
        return {"ok": False, "steps": steps, "result": None, "reason": "no_matching_tool", "source": "checkpoint_proposed"}
    intent_check = plan_matches_intent(ask, steps)
    if not intent_check["fires"]:
        # The plan named only real primitives, but none of them actually
        # matches what this ask's own question form looks like it wants --
        # the deterministic override for the failure this module's live
        # testing found: the model defaulting to its one favorite generic
        # plan regardless of fit, instead of ever using the NO_MATCH escape
        # it was explicitly offered. Reported the same way an explicit
        # NO_MATCH is, since that is what this plan should have been.
        return {
            "ok": False,
            "steps": steps,
            "result": None,
            "reason": "no_matching_tool",
            "intent_check": intent_check,
            "source": "checkpoint_proposed",
        }
    return _run_plan(steps, passages, source="checkpoint_proposed")
