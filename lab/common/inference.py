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

from lab.common.connectives import Operator, find_connectives
from lab.common.rules import _parser

PRONOUN_SUBJECTS = {"he", "she", "it", "they", "him", "her", "them", "someone", "anyone", "somebody", "something", "one"}
POSSESSIVE_PRONOUNS = {"my", "your", "his", "her", "its", "our", "their"}

_ALTERNATIVE_SEP_RE = re.compile(r";\s*")  # pure punctuation -- no word is matched here


def _strip_leading_combinator(alternative: str) -> str:
    """"unless A; B; or C" splits on ";" into ["A", "B", "or C"] -- the
    trailing alternative's own leading "or" is not part of its condition
    text. Stripping it used to be a second hardcoded regex match on the
    literal word "or" (`(?:or\\s+)?` inside the old _EXCEPTION_ALT_RE) --
    the exact same violation _UNLESS_RE was, just in the alternative-
    splitter instead of the exception-splitter. Finds the leading
    combinator the same structural way: lab.common.connectives.
    find_connectives detects "or"/"and" via spaCy's `cc` dependency
    (Operator.COMBINATOR_OR/_AND), and this only strips a match whose own
    anchor_text actually starts this fragment -- not just any "or"/"and"
    appearing anywhere inside it (a real alternative is often itself full
    of internal "or"s, e.g. "exercise or defence of legal claims").
    """
    alternative = alternative.strip()
    for match in find_connectives(alternative):
        if match.operator in (Operator.COMBINATOR_AND, Operator.COMBINATOR_OR) and alternative.lower().startswith(match.anchor_text.lower() + " "):
            return alternative[len(match.anchor_text) :].strip()
    return alternative


def _find_condition_match(consequence: str):
    """The one connective, if any, that gates this consequence -- either
    polarity. CONDITION_NEGATIVE (unless/except/except that) blocks the
    consequence if its own clause is TRUE; CONDITION_POSITIVE (provided
    that/only if/as long as/in case) blocks it if its own clause is FALSE
    -- opposite logical roles for the same trailing-clause position, which
    is exactly why EXP-026's own goal ("code rules for except, unless, and
    provided that") would have been wrong to treat all three identically.
    Only the first match (leftmost) is used, matching the old single-
    "unless" regex's maxsplit=1 behavior.
    """
    matches = [m for m in find_connectives(consequence) if m.operator in (Operator.CONDITION_NEGATIVE, Operator.CONDITION_POSITIVE)]
    return matches[0] if matches else None


def split_exception(consequence: str) -> tuple[str, str | None]:
    """Splits a consequence clause's trailing exception/condition clause
    off, the one rule shape lab.common.rules.parse_conditional_rule's own
    docstring names as a known, unparsed limit ("a rule with an exception
    is not parsed here"). Returns (consequence_without_condition,
    condition_text_or_None) -- polarity-agnostic, since
    instantiate_consequence (its only caller) just needs the consequence
    text with any trailing gate stripped, regardless of which way the gate
    points.

    EXP-091/EXP-026: finds the clause via lab.common.connectives.
    find_connectives's structural detection (both CONDITION_NEGATIVE and
    CONDITION_POSITIVE), not a literal keyword regex on the single word
    "unless". This project's earlier _UNLESS_RE regex here was exactly the
    hardcoding the project owner ruled out: it could never recognize
    "except"/"except that"/"provided that" phrasing a real statute (GDPR
    itself uses "except"). The connective's own anchor_text (its exact
    surface form) locates the split point in the original string -- the
    same single-point split the old regex did, just at a position grammar
    decided was a genuine subordinating connective instead of one
    hardcoded word.
    """
    match = _find_condition_match(consequence)
    if match is None:
        return consequence.strip(), None
    idx = consequence.lower().find(match.anchor_text.lower())
    if idx == -1:
        return consequence.strip(), None
    before, after = consequence[:idx], consequence[idx + len(match.anchor_text) :]
    return before.strip().rstrip(","), after.strip().rstrip(".")


def split_exceptions(consequence: str) -> tuple[str, list[str], str | None]:
    """Same clause split as split_exception, but the condition itself may
    be a disjunction of several alternatives ("unless A; B; or C")
    instead of exactly one -- GDPR Art 9's actual shape (one prohibition,
    three listed exceptions, any one of which blocks it), not the single-
    exception toy rule EXP-083 measured -- AND, since EXP-026, aware of
    which polarity gates the consequence: "negative" for unless/except/
    except that (blocks if the condition is true), "positive" for
    provided that/only if/as long as/in case (blocks if the condition is
    FALSE -- the opposite). check_exceptions below needs this to apply the
    opposite combination rule; every earlier caller only ever saw negative
    conditions, so this is a strict generalization of the shape, not a
    behavior change for existing "unless"/"except" rules.

    Alternatives are split on ";" (optionally followed by "or") only, never
    on a bare "," or "or" -- a real exception clause is itself often full of
    internal commas and "or"s ("the establishment, exercise or defence of
    legal claims or whenever courts are acting in their judicial
    capacity"), so splitting on those would shred one alternative into
    several. The semicolon is the only separator this function treats as
    "a new alternative starts here". Returns (consequence_without_condition,
    list_of_conditions, polarity_or_None) -- an empty list and None
    polarity when there is no condition clause at all, a one-item list for
    a single condition (the exact same text split_exception would have
    returned), so this is a strict generalization, not a different rule
    shape.
    """
    match = _find_condition_match(consequence)
    if match is None:
        return consequence.strip(), [], None
    idx = consequence.lower().find(match.anchor_text.lower())
    before, after = consequence[:idx], consequence[idx + len(match.anchor_text) :]
    condition_text = after.strip().rstrip(".")
    alternatives = [_strip_leading_combinator(alt) for alt in _ALTERNATIVE_SEP_RE.split(condition_text) if alt.strip()]
    polarity = "negative" if match.operator == Operator.CONDITION_NEGATIVE else "positive"
    return before.strip().rstrip(","), alternatives, polarity


def _clauses(consequence: str) -> list[str]:
    """Top-level conjunction split only ("X and Y" -> ["X", "Y"]), found
    structurally rather than by matching every occurrence of the literal
    word "and" (the old `re.split(r"\\band\\b", ...)` here -- the same
    class of hardcoding _UNLESS_RE was elsewhere in this module, and wrong
    on top of it: "the registration and license will be suspended" is ONE
    clause with a compound subject, and the old regex would have shredded
    it into two meaningless fragments, "the registration" and "license
    will be suspended").

    A split point is an "and" token whose dependency label is "cc", whose
    head is the sentence's own main verb/auxiliary, AND which has a
    sibling "conj" token that is itself a verb/auxiliary -- i.e. two
    independent clauses coordinated by "and", confirmed structurally, not
    one clause's compound subject/object sharing a single verb. Checked
    directly against spaCy's real parse (not assumed from a textbook
    heuristic): "it is a crime and he will go to jail" has "and" headed by
    "is" (ROOT AUX) with a sibling "go" (conj VERB) -- splits correctly;
    "the registration and license will be suspended" has "and" headed by
    "registration" (a NOUN, not a verb) -- does not split.
    """
    doc = _parser()(consequence)
    split_points = [
        tok.i
        for tok in doc
        if tok.dep_ == "cc"
        and tok.lemma_.lower() == "and"
        and tok.head.pos_ in ("VERB", "AUX")
        and any(child.dep_ == "conj" and child.pos_ in ("VERB", "AUX") for child in tok.head.children)
    ]
    if not split_points:
        return [consequence.strip()] if consequence.strip() else []
    clauses, start = [], 0
    for idx in split_points:
        clauses.append(doc[start:idx].text.strip())
        start = idx + 1
    clauses.append(doc[start:].text.strip())
    return [c for c in clauses if c]


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


def find_causal_justification(consequence: str) -> str | None:
    """A rule's consequence may carry its own "because"/"since"/"as"
    clause (Operator.CAUSAL) -- never a gate (EXP-090's own docstring:
    "a justification, never a gate that could block anything"), so it is
    never passed to check_exceptions/check_exception the way CONDITION_
    NEGATIVE/POSITIVE clauses are. spaCy's own attachment already keeps
    it from polluting _extract_clause_predicate's object text (a CAUSAL
    clause's "mark" token attaches to its own advcl verb, a sibling of
    the main clause's acomp/attr, never inside that complement's own
    subtree -- verified directly, not assumed), so there was never a
    correctness bug here. This only SURFACES the clause as its own named
    field (instead of it riding along silently inside the rule's `raw`
    text) so a caller can show the reasoning, not just the conclusion.
    """
    matches = [m for m in find_connectives(consequence) if m.operator == Operator.CAUSAL]
    if not matches:
        return None
    match = matches[0]
    idx = consequence.lower().find(match.anchor_text.lower())
    if idx == -1:
        return None
    return consequence[idx + len(match.anchor_text) :].strip().rstrip(".")


def instantiate_consequence(rule: dict, fact: dict) -> list[dict]:
    """A matched rule's consequence, turned into one or more new derived
    facts bound to the specific entity the fact named -- not the raw
    consequence string lab.common.rules.apply_rule already returns
    unchanged. One clause can yield zero, one, or more predicates
    (a clause spaCy can't parse into subject+predicate is skipped, not
    guessed). Each derived predicate carries the consequence's own
    CAUSAL justification (find_causal_justification), if any, as a
    named field -- never used to gate the derivation itself.
    """
    consequence_text, _ = split_exception(rule["consequence"])
    justification = find_causal_justification(rule["consequence"])
    derived = []
    for clause in _clauses(consequence_text):
        predicate = _extract_clause_predicate(clause, bound_subject=fact["subject"])
        if predicate is not None:
            predicate["justification"] = justification
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


def check_exceptions(exception_conditions: list[str], context_texts: list[str], polarity: str = "negative", tau: float = 0.75) -> dict:
    """OR-combines `check_exception`'s own three-way verdict across every
    alternative condition in a disjunction ("unless A, B, or C" or
    "provided that A, B, or C") -- `check_exception` itself is unchanged,
    called once per alternative, exactly the same bounded per-condition
    NLI judgment it always made.

    The returned `status` always means the same thing regardless of
    `polarity`: "holds" -> block the consequence, "not_holds" -> proceed
    cleanly, "unknown" -> proceed but flag as unresolved -- so every
    caller (lab.common.brain.reason, forward_chain) keeps checking
    status=="holds"/"unknown" exactly as it already did; this function
    absorbs the polarity difference (EXP-026) internally rather than
    pushing it onto callers.

    polarity="negative" (unless/except -- blocks if the condition is
    TRUE), in the same honest-abstention spirit as the single-exception
    case:
      - any alternative `holds` -> overall `holds` (blocked -- it only
        takes one of several listed exceptions to apply).
      - none holds, and every alternative is `unknown` -> overall
        `unknown` (nothing in the given context speaks to any of them, so
        the consequence is still derived but marked conditional).
      - none holds, and at least one is confidently `not_holds` -> overall
        `not_holds` (derives cleanly; the context doesn't have to rule out
        every alternative individually).

    polarity="positive" (provided that/only if/as long as/in case --
    blocks if the condition is FALSE, the mirror image):
      - any alternative `holds` -> overall `not_holds` (proceeds cleanly
        -- it only takes one of several listed ways of satisfying the
        condition).
      - every alternative is confidently `not_holds` -> overall `holds`
        (blocked -- the condition is confirmed false in every listed
        form, not just unconfirmed).
      - otherwise (a mix including at least one `unknown`, none `holds`)
        -> overall `unknown` (the condition isn't confirmed true anywhere,
        but isn't confirmed false everywhere either -- proceed flagged,
        never silently assume the gate failed).

    An empty list (no condition clause at all) returns `no_exception`,
    same as `check_exception(None, ...)`.
    """
    if not exception_conditions:
        return {"status": "no_exception", "per_exception": []}
    results = [check_exception(condition, context_texts, tau=tau) for condition in exception_conditions]
    any_holds = any(r["status"] == "holds" for r in results)
    all_unknown = all(r["status"] == "unknown" for r in results)
    all_not_holds = all(r["status"] == "not_holds" for r in results)
    if polarity == "negative":
        status = "holds" if any_holds else "unknown" if all_unknown else "not_holds"
    else:
        status = "not_holds" if any_holds else "holds" if all_not_holds else "unknown"
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
            _, exception_conditions, polarity = split_exceptions(rule["consequence"])
            for fact in known:
                if fact.get("subject") is None or fact["verb_lemma"] != rule["trigger_lemma"]:
                    continue
                exception_result = check_exceptions(exception_conditions, context_texts, polarity or "negative")
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
