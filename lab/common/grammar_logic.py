"""Deterministic grammar-STRUCTURE transforms -- sentence splitting and a
best-effort passive-to-active voice conversion -- the piece
`plain_language.py` explicitly says it is NOT ("this module only ever
swaps vocabulary; it has no mechanism to split a sentence, reorder a
clause, or convert passive to active voice").

Research first (AUDIT.md, "a project-wide parser upgrade", 2026-11-10),
not guessed: no deterministic rule set for either transform is assumed
safe. Every output here is gated by `preserves_meaning` (bidirectional
NLI entailment, the established pattern for verifying a rewrite keeps
its meaning) before being trusted; a transform that fails the gate -- or
whose structural preconditions aren't met at all -- returns the
ORIGINAL text unchanged, same "never guess, report the gap honestly"
discipline as `concept_tools.teach_and_run`.

Both transforms are narrowly scoped ON PURPOSE, not silently incomplete:
- `split_on_connective` only splits at a connective `lab.common.
  connectives.find_connectives` already structurally detects (never a
  keyword scan), and only when both resulting halves actually have
  usable clause text.
- `passive_to_active` only fires on a MODAL passive with an explicit
  "by"-agent ("X shall be given BY Y" -> "Y shall give X") -- the one
  subset that needs no verb re-conjugation (a modal governs the verb's
  base form either way) and is fully recoverable from the sentence
  alone. An agentless passive ("the notice shall be given", no "by X")
  or a non-modal passive ("the notice was given") is left untouched:
  both would require either inventing an agent that isn't in the text,
  or real verb conjugation this module does not attempt. A published
  rule-based attempt at the general case caps at ~50% accuracy
  (AUDIT.md's own research citation) -- this module does not try to be
  that general attempt, it covers the one safe, common-in-legal-text
  subset instead.
"""

from __future__ import annotations

from lab.common.connectives import find_connectives

NLI_TAU = 0.75  # same threshold rules.semantic_apply_rule already uses


def preserves_meaning(original: str, rewritten: str, tau: float = NLI_TAU) -> dict:
    """Bidirectional NLI entailment: `rewritten` is accepted only if it
    entails `original` AND `original` entails `rewritten`, with no
    contradiction either direction -- the established pattern (AUDIT.md
    cites the source) for checking a rewrite is logically equivalent to
    the original, not just similar-looking. Reused as the one shared
    gate for every transform in this module, so a future transform
    doesn't need its own ad hoc safety check.
    """
    from lab.common.real_encoders import real_nli

    forward = real_nli(original, rewritten)
    backward = real_nli(rewritten, original)
    ok = (
        forward["entail"] >= tau and forward["contradict"] < 0.2
        and backward["entail"] >= tau and backward["contradict"] < 0.2
    )
    return {"ok": ok, "forward": forward, "backward": backward}


def _cap_sentence(text: str) -> str:
    text = text.strip().rstrip(".,;:")
    if not text:
        return text
    text = text[:1].upper() + text[1:]
    return text if text.endswith((".", "!", "?")) else text + "."


def _span(tokens) -> str:
    return " ".join(t.text for t in tokens if not (t.dep_ == "punct" and t.text in (",", ".")))


def _find_connective_token(doc, match):
    """`find_connectives`'s own `anchor_text`/`clause_text` fields serve
    its ORIGINAL purpose (discourse-relation classification for
    `template_rewriter.choose_connective`), not clause splitting -- they
    don't hand back the independent clause's own span at all. Re-finds
    the actual matched token in a fresh parse of the same text instead
    of duplicating `connectives.py`'s own subordinator/coordinator
    vocabulary here, so this module never hardcodes a second copy of
    that closed list.
    """
    want_dep = "mark" if match.dep_pattern.startswith("mark") else match.dep_pattern
    for t in doc:
        if t.dep_ == want_dep and t.text.lower() == match.phrase.split()[0]:
            return t
    return None


def split_on_connective(text: str) -> dict:
    """Splits one long sentence into two at its first genuine discourse
    connective, for the two supported dependency shapes: a subordinate
    clause ("mark+advcl" -- because/although/while/...) or a coordinated
    clause ("cc" -- and/but/or). Returns `{"text", "split": bool,
    "reason"}` -- `reason` is `None` on a real split, or one of
    "no_connective"/"pattern_not_supported"/"incomplete_half"/
    "nli_gate_failed" when it falls back to the original text unchanged.
    Each half is also checked with `sentence_completeness.
    is_complete_sentence` before the NLI gate even runs -- catches a
    degenerate split (e.g. a bare connective word left dangling as its
    own "sentence") structurally, cheaply, before paying for a model call.
    """
    from lab.common.rules import _parser
    from lab.common.sentence_completeness import is_complete_sentence

    matches = find_connectives(text)
    if not matches:
        return {"text": text, "split": False, "reason": "no_connective"}
    match = matches[0]

    doc = _parser()(text)
    conn_tok = _find_connective_token(doc, match)
    if conn_tok is None:
        return {"text": text, "split": False, "reason": "pattern_not_supported"}

    if match.dep_pattern.startswith("mark") and conn_tok.dep_ == "mark":
        sub_verb = conn_tok.head
        root_verb = sub_verb.head
        sub_tokens = sorted((t for t in sub_verb.subtree if t.i != conn_tok.i), key=lambda t: t.i)
        exclude = {t.i for t in sub_verb.subtree}
        main_tokens = sorted((t for t in root_verb.subtree if t.i not in exclude), key=lambda t: t.i)
        clause_a, clause_b = _span(sub_tokens), _span(main_tokens)
    elif match.dep_pattern == "cc" and conn_tok.dep_ == "cc":
        first_verb = conn_tok.head
        second_verb = next((c for c in first_verb.children if c.dep_ == "conj"), None)
        if second_verb is None:
            return {"text": text, "split": False, "reason": "pattern_not_supported"}
        exclude = {t.i for t in second_verb.subtree} | {conn_tok.i}
        first_tokens = sorted((t for t in first_verb.subtree if t.i not in exclude), key=lambda t: t.i)
        clause_a, clause_b = _span(first_tokens), _span(sorted(second_verb.subtree, key=lambda t: t.i))
    else:
        return {"text": text, "split": False, "reason": "pattern_not_supported"}

    sent_a, sent_b = _cap_sentence(clause_a), _cap_sentence(clause_b)
    if not sent_a or not sent_b:
        return {"text": text, "split": False, "reason": "incomplete_half"}
    if not (is_complete_sentence(sent_a)["complete"] and is_complete_sentence(sent_b)["complete"]):
        return {"text": text, "split": False, "reason": "incomplete_half"}

    candidate = f"{sent_a} {sent_b}"
    gate = preserves_meaning(text, candidate)
    if not gate["ok"]:
        return {"text": text, "split": False, "reason": "nli_gate_failed", "gate": gate}
    return {"text": candidate, "split": True, "reason": None, "connective": match.phrase, "gate": gate}


def passive_to_active(text: str) -> dict:
    """Converts a MODAL passive with an explicit "by"-agent to active
    voice ("the notice shall be given by the Lessor" -> "the Lessor
    shall give the notice"). Returns `{"text", "converted": bool,
    "reason"}` -- `reason` is `None` on a real conversion, or
    "not_modal_passive_with_agent"/"nli_gate_failed" when it falls back
    to the original text unchanged. See module docstring for exactly
    which passive shapes this does NOT attempt.
    """
    from lab.common.rules import _parser

    doc = _parser()(text)
    root = next((t for t in doc if t.dep_ == "ROOT" and t.pos_ == "VERB"), None)
    if root is None:
        return {"text": text, "converted": False, "reason": "not_modal_passive_with_agent"}

    children = {c.dep_: c for c in root.children}
    modal = children.get("aux")
    auxpass = children.get("auxpass")
    nsubjpass = children.get("nsubjpass")
    agent = children.get("agent")
    if not (modal and modal.tag_ == "MD" and auxpass and nsubjpass and agent):
        return {"text": text, "converted": False, "reason": "not_modal_passive_with_agent"}
    agent_obj = next((c for c in agent.children if c.dep_ == "pobj"), None)
    if agent_obj is None:
        return {"text": text, "converted": False, "reason": "not_modal_passive_with_agent"}

    def span(token) -> str:
        return " ".join(t.text for t in sorted(token.subtree, key=lambda t: t.i))

    neg = children.get("neg")
    skip_deps = {"aux", "auxpass", "nsubjpass", "agent", "neg", "punct"}
    other_children = sorted(
        (c for c in root.children if c.dep_ not in skip_deps), key=lambda t: t.i
    )
    # A child token-ordered BEFORE the passive subject in the original
    # sentence ("DESPITE THIS, the notice must be given...") is a
    # fronted/preposed adverbial, not a trailing modifier -- it has to
    # stay at the front of the rebuilt sentence too, or it lands in the
    # middle of the new object/verb ("...give the notice despite this to
    # the Lessee"), wrong. Found by direct testing, not assumed: the
    # first version of this function always appended every remaining
    # child after the object, in original token order, which is only
    # correct for a TRAILING modifier like "to the Lessee".
    preposed = [c for c in other_children if c.i < nsubjpass.i]
    postposed = [c for c in other_children if c.i >= nsubjpass.i]

    def lower_first(s: str) -> str:
        return s[:1].lower() + s[1:] if s else s

    preposed_spans = [span(c) for c in preposed]
    if preposed_spans:
        preposed_spans[-1] += ","
    parts = [
        *preposed_spans,
        span(agent_obj),
        modal.text,
        *(["not"] if neg else []),
        root.lemma_,
        lower_first(span(nsubjpass)),
        *(lower_first(span(c)) for c in postposed),
    ]
    candidate = _cap_sentence(" ".join(p for p in parts if p))

    gate = preserves_meaning(text, candidate)
    if not gate["ok"]:
        return {"text": text, "converted": False, "reason": "nli_gate_failed", "gate": gate}
    return {"text": candidate, "converted": True, "reason": None, "gate": gate}
