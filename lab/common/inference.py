"""Multi-step symbolic inference: the project owner's own proposal, built
and scoped honestly -- convert a stated rule and a stated fact into
predicate form and let deterministic code chain the consequences, instead
of asking any model to "reason it out."

The motivating example, verbatim: "Rohan killed Arun. If anyone kills
another person, it is a crime and he will go to jail." -> kills(Rohan,
Arun) unified against kills(X, Y) -> crime(X), jail(X) -> derive crime
(Rohan), jail(Rohan). "Multi-step" means a derived fact (jail(Rohan)) can
itself trigger a further rule (jail(X) -> license_suspended(X)) in the
next round, the standard forward-chaining fixpoint loop every Prolog/
Datalog engine runs -- not a new idea, just not previously built here.

Every extraction step is spaCy's dependency parser (lab.common.rules'
existing non-generative parser, loaded once via lab.common.real_models)
or the real DeBERTa-v3 NLI classifier (lab.common.real_encoders) for one
bounded judgment (does this context entail that exception). No generative
model anywhere in this module -- the project owner's own explicit
requirement, not an afterthought: converting language into a rule/fact
representation is exactly the step most at risk of inventing something
that was never actually stated, so it is done by the same syntactic
parser and classifier already measured and used elsewhere in this repo,
never by a model that writes free text.

Named, upfront limit: a rule's "unless <exception>" clause is checked
against whatever context text is given, using NLI entailment -- if the
context affirmatively states the exception, the rule's consequence is
suppressed; if the context contradicts it, the consequence stands; if
the context says nothing either way, the engine does NOT assume the
exception is false just because it found no evidence for it. It derives
the consequence anyway but marks it "unresolved_exception" -- visibly
conditional, not silently confident. A real legal determination with an
unresolved exception should never read as equivalent to one with no
exception at all.
"""

from __future__ import annotations

import re

from lab.common.rules import _parser

PRONOUN_SUBJECTS = {"he", "she", "it", "they", "him", "her", "them", "someone", "anyone", "somebody", "something", "one"}
POSSESSIVE_PRONOUNS = {"my", "your", "his", "her", "its", "our", "their"}

_UNLESS_RE = re.compile(r"\bunless\b", re.I)
_EXCEPTION_ALT_RE = re.compile(r";\s*(?:or\s+)?", re.I)


def split_exception(consequence: str) -> tuple[str, str | None]:
    """Splits a consequence clause's trailing "...unless <condition>" off,
    the one rule shape lab.common.rules.parse_conditional_rule's own
    docstring names as a known, unparsed limit ("a rule with an exception
    is not parsed here"). Returns (consequence_without_exception,
    exception_condition_or_None).
    """
    parts = _UNLESS_RE.split(consequence, maxsplit=1)
    if len(parts) == 1:
        return consequence.strip(), None
    return parts[0].strip().rstrip(","), parts[1].strip().rstrip(".")


def split_exceptions(consequence: str) -> tuple[str, list[str]]:
    """Same trailing "...unless <condition>" split as split_exception, but
    the condition itself may be a disjunction of several alternative
    exceptions ("unless A; B; or C") instead of exactly one -- GDPR Art 9's
    actual shape (one prohibition, three listed exceptions, any one of
    which blocks it), not the single-exception toy rule EXP-083 measured.

    Alternatives are split on ";" (optionally followed by "or") only, never
    on a bare "," or "or" -- a real exception clause is itself often full of
    internal commas and "or"s ("the establishment, exercise or defence of
    legal claims or whenever courts are acting in their judicial
    capacity"), so splitting on those would shred one alternative into
    several. The semicolon is the only separator this function treats as
    "a new alternative starts here". Returns (consequence_without_exception,
    list_of_exception_conditions) -- an empty list when there is no "unless"
    clause at all, a one-item list for a single exception (the exact same
    condition split_exception would have returned), so this is a strict
    generalization, not a different rule shape.
    """
    consequence_without, exception_text = split_exception(consequence)
    if exception_text is None:
        return consequence_without, []
    alternatives = [alt.strip() for alt in _EXCEPTION_ALT_RE.split(exception_text) if alt.strip()]
    return consequence_without, alternatives


def _clauses(consequence: str) -> list[str]:
    """Top-level conjunction split only ("X and Y" -> ["X", "Y"]) -- the
    same deliberately shallow approach lab.common.intent_signals' own
    clause splitter uses, not a general parser for arbitrary nested
    conjunctions.
    """
    return [c.strip() for c in re.split(r"\band\b", consequence, flags=re.I) if c.strip()]


def _extract_clause_predicate(clause: str, bound_subject: str) -> dict | None:
    """One consequence clause -> one predicate, with any pronoun or
    missing subject bound to the entity that satisfied the rule's
    trigger (the fact's own subject) -- "he will go to jail" said about
    Rohan's act means Rohan goes to jail, not some unbound "he".

    Handles both a verb-object clause ("he will go to jail" ->
    go/jail, via the same prepositional-object fallback lab.common.
    rules.extract_fact_triple already uses) and a copula clause ("it is
    a crime" -> be/crime) -- extract_fact_triple itself only handles the
    former (its own root.pos_ != "VERB" check rejects a copula root),
    which consequence clauses are just as often phrased as, so this is a
    genuinely separate case, not a copy of that function.

    A possessive-pronoun subject ("their license will be suspended") is
    also bound to the triggering entity, not left as its own free-
    standing subject -- found needed when a first version of this
    function derived subject="license" for exactly this clause, losing
    the fact that it is Rohan's license, not an unrelated entity named
    "license". The possessed noun becomes this predicate's object
    instead ((Rohan, suspend, license), not (license, suspend, None)).
    """
    doc = _parser()(clause)
    root = next((t for t in doc if t.dep_ == "ROOT" and t.pos_ in ("VERB", "AUX")), None)
    if root is None:
        return None

    subject = next((t for t in root.children if t.dep_ in ("nsubj", "nsubjpass")), None)
    subject_text = subject.text.lower() if subject is not None else None
    possessive = next((t for t in subject.children if t.dep_ == "poss" and t.text.lower() in POSSESSIVE_PRONOUNS), None) if subject is not None else None

    if subject is None or subject_text in PRONOUN_SUBJECTS:
        resolved_subject, possessed_object = bound_subject, None
    elif possessive is not None:
        resolved_subject = bound_subject
        possessed_object = " ".join(t.text for t in sorted(subject.subtree, key=lambda t: t.i) if t is not possessive)
    else:
        resolved_subject, possessed_object = subject.text, None

    if root.pos_ == "AUX":
        complement = next((t for t in root.children if t.dep_ in ("attr", "acomp")), None)
        if complement is None:
            return None
        return {"subject": resolved_subject, "verb_lemma": "be", "object": " ".join(t.text for t in sorted(complement.subtree, key=lambda t: t.i)), "raw": clause}

    obj = next((t for t in root.children if t.dep_ in ("dobj", "attr", "dative")), None)
    if obj is None:
        prep = next((t for t in root.children if t.dep_ == "prep"), None)
        if prep is not None:
            obj = next((t for t in prep.children if t.dep_ == "pobj"), None)
    object_text = " ".join(t.text for t in sorted(obj.subtree, key=lambda t: t.i)) if obj is not None else possessed_object
    return {
        "subject": resolved_subject,
        "verb_lemma": root.lemma_.lower(),
        "object": object_text,
        "raw": clause,
    }


def instantiate_consequence(rule: dict, fact: dict) -> list[dict]:
    """A matched rule's consequence, turned into one or more new derived
    facts bound to the specific entity the fact named -- not the raw
    consequence string lab.common.rules.apply_rule already returns
    unchanged. One clause can yield zero, one, or more predicates
    (a clause spaCy can't parse into subject+predicate is skipped, not
    guessed).
    """
    consequence_text, _ = split_exception(rule["consequence"])
    derived = []
    for clause in _clauses(consequence_text):
        predicate = _extract_clause_predicate(clause, bound_subject=fact["subject"])
        if predicate is not None:
            derived.append(predicate)
    return derived


def check_exception(exception_condition: str | None, context_texts: list[str], tau: float = 0.75) -> dict:
    """Does any given context text affirmatively state the exception
    holds, contradict it, or say nothing either way -- three outcomes,
    not two. "unknown" is the honest default: absence of stated evidence
    is not evidence of absence, and this engine does not silently treat
    them as the same thing, the same posture lab.common.brain's
    "ungrounded" decision already takes for a different gap.
    """
    if exception_condition is None:
        return {"status": "no_exception", "best_entail": None, "best_contradict": None, "best_context": None}
    if not context_texts:
        return {"status": "unknown", "best_entail": 0.0, "best_contradict": 0.0, "best_context": None}

    from lab.common.real_encoders import real_nli

    best_entail, best_contradict, best_context = 0.0, 0.0, None
    for text in context_texts:
        probs = real_nli(text, exception_condition)
        if probs["entail"] > best_entail:
            best_entail, best_context = probs["entail"], text
        if probs["contradict"] > best_contradict:
            best_contradict = probs["contradict"]
    if best_entail >= tau:
        status = "holds"
    elif best_contradict >= tau:
        status = "not_holds"
    else:
        status = "unknown"
    return {"status": status, "best_entail": round(best_entail, 4), "best_contradict": round(best_contradict, 4), "best_context": best_context}


def check_exceptions(exception_conditions: list[str], context_texts: list[str], tau: float = 0.75) -> dict:
    """OR-combines `check_exception`'s own three-way verdict across every
    alternative exception condition in a disjunction ("unless A, B, or C")
    -- `check_exception` itself is unchanged, called once per alternative,
    exactly the same bounded per-exception NLI judgment it always made.

    Combination, in the same honest-abstention spirit as the single-
    exception case:
      - any alternative `holds` -> overall `holds` (the rule's consequence
        is blocked -- it only takes one of several listed exceptions to
        apply).
      - none holds, and every alternative is `unknown` -> overall
        `unknown` (nothing in the given context speaks to any of them, so
        the consequence is still derived but marked conditional, never
        silently treated as if no exception could possibly apply).
      - none holds, and at least one is confidently `not_holds` -> overall
        `not_holds` (the consequence derives cleanly; the context doesn't
        have to rule out every alternative individually, only none may
        hold and at least one must be confidently ruled out).
    An empty list (no "unless" clause at all) returns `no_exception`, same
    as `check_exception(None, ...)`.
    """
    if not exception_conditions:
        return {"status": "no_exception", "per_exception": []}
    results = [check_exception(condition, context_texts, tau=tau) for condition in exception_conditions]
    if any(r["status"] == "holds" for r in results):
        status = "holds"
    elif all(r["status"] == "unknown" for r in results):
        status = "unknown"
    else:
        status = "not_holds"
    return {"status": status, "per_exception": results}


def forward_chain(facts: list[dict], rules: list[dict], context_texts: list[str] | None = None, max_steps: int = 10) -> dict:
    """Repeatedly matches every rule against every known fact, derives new
    facts (instantiate_consequence), and feeds those back in as candidate
    facts for the next round -- the standard forward-chaining fixpoint
    loop, stopping when a round derives nothing new or `max_steps` is hit
    (a real cap, so a malformed rule set can't loop forever).

    Returns {"facts": all facts (given + derived), "trace": one entry per
    derivation naming exactly which rule and which fact produced it, plus
    the exception check's own result, "steps": rounds actually run}.
    Every derived fact's provenance is in the trace -- nothing is a black
    box, and a fact derived under an unresolved exception is visibly
    marked `conditional=True`, never indistinguishable from a clean one.
    """
    context_texts = context_texts or []
    known = list(facts)
    seen_signatures = {(f["subject"], f["verb_lemma"], f.get("object")) for f in known if f.get("subject")}
    trace = []
    step = 0
    for step in range(max_steps):
        new_this_step = []
        for rule in rules:
            _, exception_conditions = split_exceptions(rule["consequence"])
            for fact in known:
                if fact.get("subject") is None or fact["verb_lemma"] != rule["trigger_lemma"]:
                    continue
                exception_result = check_exceptions(exception_conditions, context_texts)
                if exception_result["status"] == "holds":
                    trace.append({"step": step, "rule": rule["raw"], "fact": fact["raw"], "derived": None, "blocked_by_exception": exception_result})
                    continue
                for derived_fact in instantiate_consequence(rule, fact):
                    signature = (derived_fact["subject"], derived_fact["verb_lemma"], derived_fact.get("object"))
                    if signature in seen_signatures:
                        continue
                    seen_signatures.add(signature)
                    derived_fact["conditional"] = exception_result["status"] == "unknown"
                    derived_fact["derivation"] = {"rule": rule["raw"], "fact": fact["raw"], "exception_check": exception_result}
                    new_this_step.append(derived_fact)
                    trace.append({"step": step, "rule": rule["raw"], "fact": fact["raw"], "derived": derived_fact, "blocked_by_exception": None})
        if not new_this_step:
            break
        known.extend(new_this_step)
    return {"facts": known, "trace": trace, "steps": step + 1 if trace else 0}
