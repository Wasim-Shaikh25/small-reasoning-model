"""Decide, before ever calling a generative checkpoint, whether a finding's
statement already needs no rewrite at all -- zero LLM calls for the common
case, instead of calling generate() first and discovering after the fact
(via fidelity_gate) that it never had anything to fix.

Built after measuring (AUDIT.md, 2026-11-09, "fluency does not require a
generative model...") that EXP-063's AND EXP-081's fixtures -- two
unrelated real fixtures, one handwritten, one a real GDPR excerpt -- both
scored 0% generative success already: every leaf fell back to the
deterministic renderer regardless of checkpoint (flan-t5-small, Qwen,
gemma3). This module asks the structural question underneath that result
directly: `build_prompt`'s own instruction is literally "rewrite ... as
one grammatically correct sentence" -- if the source statement already IS
one, there's nothing for a model to do but restate it, and restating it is
exactly what the deterministic renderer already does for free. Running
this gate on the same two fixtures found that's true for all 69 statements
across both, for two different, individually-verified reasons: EXP-063's
13 statements are all `ok`; EXP-081's 69 real findings are 56 `ok` plus 13
`no_verbal_root` -- checked individually by printing every flagged
statement, not assumed from a flag -- of which 12 are verbatim article
headings ("Art. 83 GDPR\\nGeneral conditions for imposing administrative
fines") and 1 is a genuine lead-in fragment ("For the purposes of this
Regulation:") with no main verb of its own. Neither kind is a broken
sentence a generative rewrite could legitimately "fix": forcing a heading
into "one grammatical sentence" fabricates structure the source never
had, and the lead-in fragment is correctly incomplete BY DESIGN -- it
introduces the clauses that follow it; `template_splice` already
sequences it next to them, which is the right deterministic treatment,
not a rewrite. So 69/69 of this real document needs zero generative
rewriting -- not one convenient flag covering all 13 (this module's own
first-draft `heading_like` sub-flag, based on token count alone, matched
only 1 of the 13 on re-check; kept below as a weak hint, not a claim).

Reuses `lab.common.real_models`' already-loaded en_core_web_sm spaCy
pipeline (the same checkpoint this project's NER already runs) for its
dependency parse only -- not a new dependency, not a new download, and not
the generative capability this module exists to make unnecessary.

Known blind spots, found by direct adversarial testing, not assumed away:
this check only catches a DANGLING trailing token (a clause cut off
mid-way, ending on a conjunction/preposition/determiner) and a missing
finite verb. It does NOT catch a gerund-only fragment ("Running quickly
down the street." parses with a VERB root and passes) or a subordinate
clause presented alone with no independent clause ("Because the tenant
did not pay." also parses with a VERB root and passes). Neither blind spot
was hit by either real fixture tested, but neither is fixed, and this
module does not claim to replace a general grammaticality checker.

This is also not a grammar OR spelling corrector -- a statement riddled
with typos ("i tryed to tork to him") still parses with a verbal root and
is reported `complete`, same scope `spellfix.py`/`informal_register.py`
already own, not duplicated here.
"""

from __future__ import annotations

_DANGLING_POS = {"CCONJ", "SCONJ", "ADP", "DET"}

_nlp = None


def _pipeline():
    global _nlp
    if _nlp is None:
        import spacy

        _nlp = spacy.load("en_core_web_sm")
    return _nlp


def is_complete_sentence(text: str) -> dict:
    """{"complete": bool, "reason": str, ...}. See module docstring for the
    exact checks and their known blind spots.

    `reason` is one of: "empty", "dangling_<cconj|sconj|adp|det>" (ends on
    a token class that can never legally end a clause), "no_verbal_root"
    (no finite verb anywhere -- a heading/label or a lead-in fragment;
    `heading_like` (token count <= 6) is a weak, token-count-only hint,
    confirmed on EXP-081's real fixture to catch only 1 of 13 genuine
    headings -- treat `no_verbal_root` itself, not `heading_like`, as the
    signal "don't force this into one sentence"), or "ok".
    """
    text = (text or "").strip()
    if not text:
        return {"complete": False, "reason": "empty"}

    doc = _pipeline()(text)
    tokens = [t for t in doc if not t.is_space]
    if not tokens:
        return {"complete": False, "reason": "empty"}

    last = tokens[-1]
    if last.pos_ in _DANGLING_POS:
        return {"complete": False, "reason": f"dangling_{last.pos_.lower()}", "last_token": last.text}

    has_verbal_root = any(t.dep_ == "ROOT" and t.pos_ in ("VERB", "AUX") for t in doc)
    if not has_verbal_root:
        return {"complete": False, "reason": "no_verbal_root", "heading_like": len(tokens) <= 6}

    return {"complete": True, "reason": "ok"}
