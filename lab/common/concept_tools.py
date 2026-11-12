"""The "teach tool" the project owner asked for by name: a YAML-defined
concept registry, so a new capability ("give me a timeline", "give me the
respondent's address", "give me every act and section cited", "which
claims are within the warranty window") is added by writing a YAML file
under `lab/common/concepts/`, never by writing a new Python function for
that specific task.

The shipped registry (`lab/common/concepts/*.yaml`, non-recursive) starts
EMPTY -- no "timeline", no "parties", no industry baked in. The four
concept files proving this layer works (timeline/acts_and_sections/
respondent_addresses/parties_name_address, all legal-petition examples)
live under `lab/common/concepts/examples/`, which `load_concepts` never
scans, precisely so a different industry doesn't inherit a legal
product's vocabulary by default -- it starts from nothing and teaches its
own concepts the same way these examples were taught.

This extends `lab.common.doc_tools`'s own already-proven rule -- "a
template is DATA, never something the model invents" -- from document
STRUCTURE to CAPABILITY: a concept's recipe (which generic primitives to
run, in what order, with what parameters) is data too. See
`lab.common.method_teaching` for the sibling, code-level mechanism this
complements (a bounded checkpoint naming primitives when nothing matches);
this module is the externally-teachable, no-checkpoint-needed front door
that is tried first.

Only `GENERIC_REGISTRY` is Python, and every entry in it is a reusable,
domain-agnostic operation parameterized by data (a label, a regex pattern,
a field name, a comparison operator) -- never a function named after one
specific task or one specific field. `structure_field`'s `parser` and
`filter_by_condition`'s `operator`/`value` follow the same rule
`extract_by_label`'s `label` already does: the primitive is generic, the
*vocabulary* it runs on is data from the YAML, never a new function. A
`concept` YAML never introduces a new primitive; it only composes existing
ones. If no concept matches and no existing primitive combination could
answer the ask, `teach_and_run` returns `ok=False` with a clear "teach me"
message -- it does not guess, and it does not call a generative model to
paper over the gap.

Concept YAML shape (see `lab/common/concepts/_example.yaml`):

    concept: timeline
    describes: >
      A chronologically ordered list of dated events, each with the
      sentence it came from.
    aliases: [timeline, chronology, "sequence of events"]
    recipe:
      - tool: extract_by_label
        label: date
      - tool: group_by_sentence
      - tool: sort_chronological

`ctx` (the data a recipe runs against) is `{"passages": [...], "records":
[...]}` -- `passages` are raw text chunks (`{"id", "text"}`), `records` are
already-structured rows (e.g. party data: `{"name", "role", "address"}`).
A primitive reads whichever of the two it needs; most read `prior` (the
previous step's output) once the chain is past its first step.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

from lab.common.calc import compare_numbers, parse_date
from lab.common.entities import detect_primary, parse_address
from lab.common.real_encoders import bge_embed
from lab.common.textutil import sentences

CONCEPTS_DIR = Path(__file__).resolve().parent / "concepts"

# Provisional, like method_teaching.INTENT_TAU -- not yet calibrated against
# a dedicated cross-domain exploration. Alias matching (exact substring) is
# tried first and is exact, not scored; this threshold only gates the
# embedding fallback for asks that don't literally contain a taught alias.
CONCEPT_TAU = 0.6


# ---- generic primitives: domain-agnostic, parameterized by data ----------


def extract_by_label(ctx: dict, prior, label: str) -> list[dict]:
    """Every span `lab.common.entities.detect_primary` tags with `label`
    (date, person, organization, amount, address, ...) across every passage.
    One primitive for every label, instead of one hardcoded function per
    label (`lab.common.method_teaching`'s `_extract_dates`/`_extract_persons`/
    `_extract_organizations`/`_extract_amounts` are the same idea, each
    frozen to one label; this is that idea generalized so a new label never
    needs a new function).
    """
    rows = list(prior or [])
    for p in ctx.get("passages", []):
        text = p.get("text", "") or ""
        for m in detect_primary(text):
            if m["label"] == label:
                rows.append({"passage_id": p["id"], "span": m["text"], "start": m["start"], "end": m["end"], "label": label})
    return rows


def extract_by_pattern(ctx: dict, prior, pattern: str, label: str = "match") -> list[dict]:
    """Every regex match of `pattern` across every passage -- the escape
    hatch for a domain-specific citation shape (a statute section, a case
    number, a policy clause id) that `detect_primary`'s fixed label set
    doesn't cover. The pattern is DATA (comes from the concept YAML), never
    a new Python function; a new domain-specific extraction is a new
    concept file, not a new primitive.
    """
    rows = list(prior or [])
    rx = re.compile(pattern)
    for p in ctx.get("passages", []):
        text = p.get("text", "") or ""
        for m in rx.finditer(text):
            rows.append({"passage_id": p["id"], "span": m.group(0), "start": m.start(), "end": m.end(), "label": label})
    return rows


def group_by_sentence(ctx: dict, prior) -> list[dict]:
    """Attaches, to each item a prior extraction step found, the sentence
    it actually occurs in -- same deterministic lookup as
    `lab.common.method_teaching._group_by_sentence`.
    """
    by_id = {p["id"]: p.get("text", "") or "" for p in ctx.get("passages", [])}
    rows = []
    for item in prior or []:
        text = by_id.get(item.get("passage_id"), "")
        for sent in sentences(text):
            if item.get("span", "") in sent:
                rows.append({**item, "sentence": sent})
                break
    return rows


def sort_chronological(ctx: dict, prior) -> list[dict]:
    """Sorts prior items by each item's own `span` parsed as a date; an
    item whose span doesn't parse as a date sorts last, never dropped.
    """

    def key(row: dict):
        parsed = parse_date(row.get("span", ""))
        return parsed or datetime.max

    return sorted(prior or [], key=key)


def filter_records(ctx: dict, prior, field: str, equals: str) -> list[dict]:
    """Keeps only the structured records (from `prior`, or `ctx["records"]`
    on a recipe's first step) whose `field` equals `equals`, case-
    insensitively -- e.g. `field: role, equals: respondent`. Generic over
    any field name; a new role or category is a new concept YAML value,
    never a new function.
    """
    records = prior if prior is not None else ctx.get("records", [])
    needle = str(equals).strip().lower()
    return [r for r in records if str(r.get(field, "")).strip().lower() == needle]


def select_fields(ctx: dict, prior, fields: list[str]) -> list[dict]:
    """Projects each structured record (from `prior`, or `ctx["records"]`
    on a recipe's first step) down to only the named fields -- "write name
    and address" is `select_fields` with `fields: [name, address]`, nothing
    task-specific.
    """
    records = prior if prior is not None else ctx.get("records", [])
    return [{f: r.get(f) for f in fields} for r in records]


STRUCTURE_PARSERS = {"address": parse_address}


def structure_field(ctx: dict, prior, field: str, parser: str) -> list[dict]:
    """Structures each item's `field` text through a named deterministic
    parser from `STRUCTURE_PARSERS` (today: `address` ->
    `lab.common.entities.parse_address`; a fixed-field extractor like a
    phone or case-number parser is added the same way later, as a
    registry entry, not a new primitive). One generic "structure this
    field with that parser" operation instead of a function named after
    one specific field -- `resolve_addresses` was retired in favor of
    this, since a primitive named after "address" is exactly the kind of
    task-named function this layer exists to avoid; `parser` is now data,
    read from the concept YAML, same as `label` on `extract_by_label`.
    """
    if parser not in STRUCTURE_PARSERS:
        raise ValueError(f"Unknown structure_field parser {parser!r}. Known: {sorted(STRUCTURE_PARSERS)}")
    fn = STRUCTURE_PARSERS[parser]
    rows = []
    for item in prior or []:
        raw = item.get(field) if isinstance(item.get(field), str) else item.get("span")
        rows.append({**item, f"{field}_parsed": fn(raw)} if raw else item)
    return rows


_CONDITION_OPS = {
    "less_than": lambda rel: rel == "less",
    "at_most": lambda rel: rel in ("less", "equal"),
    "greater_than": lambda rel: rel == "greater",
    "at_least": lambda rel: rel in ("greater", "equal"),
    "equal_to": lambda rel: rel == "equal",
}


def filter_by_condition(ctx: dict, prior, field: str, operator: str, value: str) -> list[dict]:
    """Keeps only the records whose `field` satisfies a numeric or
    date/duration `operator`/`value` comparison -- "playtime_hours
    less_than 2 hours", "days_since_purchase at_most 14 days" -- instead
    of a bespoke function per policy. This is the generic replacement for
    the structural gap named in HANDOFF.md: `lab.common.rules.apply_rule`
    only ever compares a trigger verb's lemma and never evaluates a
    quantitative or temporal condition at all, so a rule like "less than
    two hours and refunded within two weeks" matched on verb alone while
    ignoring both numbers. Here the comparison is mandatory, not
    optional: a record fails the step the moment its own value doesn't
    satisfy `operator`/`value`, whether that value is a plain number
    (`lab.common.calc.compare_numbers`) or a duration -- "2 hours"/"14
    days" are both reduced to a common number of hours (`_HOURS_PER_UNIT`)
    before comparing, and a bare record value with no unit of its own
    inherits the threshold's unit rather than being compared raw. Works
    for a refund window, a warranty period, an SLA
    deadline, a leave-balance cap, a credit limit -- any policy, any
    industry; the field name, operator and threshold are the only
    per-policy input, and all three are YAML data.
    """
    if operator not in _CONDITION_OPS:
        raise ValueError(f"Unknown condition operator {operator!r}. Known: {sorted(_CONDITION_OPS)}")
    records = prior if prior is not None else ctx.get("records", [])
    threshold_amount, threshold_unit = _parse_amount(value), _parse_unit(value)
    rows = []
    for r in records:
        actual = r.get(field)
        if actual is None:
            continue
        actual_amount = _parse_amount(actual)
        if actual_amount is None or threshold_amount is None:
            continue
        if threshold_unit:
            # A bare record value ("30", no unit) is assumed to already be
            # expressed in the threshold's own unit -- "days_since_purchase:
            # 30" compared against "14 days" is 30 DAYS, not 30 of whatever
            # unit it happened to lack. A record value that DOES carry its
            # own unit is still converted on its own terms (e.g. "1 week"
            # against "14 days" compares correctly as 7 vs 14 days).
            actual_unit = _parse_unit(actual) or threshold_unit
            a_val = actual_amount * _HOURS_PER_UNIT[actual_unit]
            t_val = threshold_amount * _HOURS_PER_UNIT[threshold_unit]
        else:
            a_val, t_val = actual_amount, threshold_amount
        comparison = compare_numbers(str(a_val), str(t_val))
        if comparison.get("ok") and _CONDITION_OPS[operator](comparison["relation"]):
            rows.append(r)
    return rows


_HOURS_PER_UNIT = {"hour": 1, "day": 24, "week": 24 * 7, "month": 24 * 30}


def _parse_unit(value) -> str | None:
    match = re.search(r"(hour|day|week|month)", str(value), re.I)
    return match.group(1).lower() if match else None


def _parse_amount(value) -> float | None:
    match = re.search(r"[\d.]+", str(value))
    return float(match.group(0)) if match else None


def count(ctx: dict, prior) -> dict:
    return {"count": len(prior or [])}


GENERIC_REGISTRY = {
    "extract_by_label": extract_by_label,
    "extract_by_pattern": extract_by_pattern,
    "group_by_sentence": group_by_sentence,
    "sort_chronological": sort_chronological,
    "filter_records": filter_records,
    "select_fields": select_fields,
    "structure_field": structure_field,
    "filter_by_condition": filter_by_condition,
    "count": count,
}


def execute_recipe(recipe: list[dict], ctx: dict) -> list | dict:
    """Runs a concept's recipe step by step, threading each step's output
    into the next as `prior` -- plain deterministic composition, same
    discipline as `lab.common.method_teaching.execute_method`. Raises
    `ValueError` for a step naming a primitive outside `GENERIC_REGISTRY`
    (a malformed or hand-typo'd concept file) rather than silently skipping it.
    """
    prior = None
    for step in recipe:
        name = step.get("tool")
        if name not in GENERIC_REGISTRY:
            raise ValueError(f"Unknown primitive {name!r} in concept recipe. Known: {sorted(GENERIC_REGISTRY)}")
        args = {k: v for k, v in step.items() if k != "tool"}
        prior = GENERIC_REGISTRY[name](ctx, prior, **args)
    return prior


# ---- loading + matching concepts ------------------------------------------


def load_concepts() -> list[dict]:
    """Every registered concept, read fresh from disk each call -- same
    "a company can add one without restarting anything" rule
    `lab.common.doc_tools.list_tools` already follows for templates.
    Non-recursive by design: `lab/common/concepts/examples/` is never
    scanned, so the shipped registry is empty until a caller adds their
    own concept file -- see this module's own docstring.
    """
    if not CONCEPTS_DIR.exists():
        return []
    concepts = []
    for f in sorted(CONCEPTS_DIR.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        concepts.append(yaml.safe_load(f.read_text(encoding="utf-8")))
    return concepts


def match_concept(ask: str, concepts: list[dict] | None = None) -> dict:
    """Exact alias substring match first (unambiguous, free); embedding
    similarity against each concept's own `describes` text as a fallback
    for an ask that doesn't literally contain a taught alias -- same
    `bge_embed` mechanism `lab.tests.support.select_template` already
    uses for template selection, reused rather than a new scheme.
    """
    concepts = concepts if concepts is not None else load_concepts()
    if not concepts:
        return {"concept": None, "score": 0.0, "method": "none_registered"}

    lowered = ask.lower()
    for c in concepts:
        for alias in c.get("aliases", []):
            if alias.lower() in lowered:
                return {"concept": c, "score": 1.0, "method": "alias"}

    descriptions = [c.get("describes") or c.get("concept", "") for c in concepts]
    vecs = bge_embed([ask, *descriptions])
    ask_vec, cand_vecs = vecs[0], vecs[1:]
    sims = cand_vecs @ ask_vec
    best_idx = int(np.argmax(sims))
    best_score = float(sims[best_idx])
    if best_score < CONCEPT_TAU:
        return {"concept": None, "score": round(best_score, 4), "method": "embedding_below_threshold"}
    return {"concept": concepts[best_idx], "score": round(best_score, 4), "method": "embedding"}


def teach_and_run(ask: str, ctx: dict, concepts: list[dict] | None = None) -> dict:
    """The one function callers use. Tries to match `ask` to a taught
    concept and run its recipe; if nothing matches, or the recipe is
    malformed, or it runs cleanly but finds nothing, returns `ok=False`
    with a `reason` that tells a caller -- or a person -- exactly which of
    the three happened, same "never guess, report the gap honestly" rule
    as `lab.common.method_teaching.teach_and_execute`.
    """
    match = match_concept(ask, concepts)
    concept = match["concept"]
    if concept is None:
        return {
            "ok": False,
            "reason": "unknown_concept",
            "ask": ask,
            "message": (
                "I don't know how to do this yet. Teach me by adding a YAML "
                "file under lab/common/concepts/ (see concepts/_example.yaml) "
                "naming the aliases this ask should match and the recipe of "
                "existing primitives to run."
            ),
            "match": match,
        }
    try:
        result = execute_recipe(concept["recipe"], ctx)
    except (ValueError, TypeError, KeyError) as exc:
        return {"ok": False, "reason": "recipe_failed", "concept": concept.get("concept"), "error": str(exc), "match": match}
    found = bool(result) and (result.get("count", 1) != 0 if isinstance(result, dict) else True)
    return {
        "ok": found,
        "reason": None if found else "ran_but_found_nothing",
        "concept": concept.get("concept"),
        "result": result,
        "match": match,
    }
