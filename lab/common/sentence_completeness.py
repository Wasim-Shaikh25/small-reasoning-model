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

Two more blind spots, found by direct adversarial testing and FIXED
(2026-11-10, HANDOFF.md): a gerund-only fragment ("Running quickly down
the street.") and a lone subordinate clause ("Because the tenant did not
pay.") both parse with a VERB ROOT and used to pass. Checked directly
against real spaCy parses before writing either rule, not assumed:
- A gerund fragment's own ROOT is tagged `VBG` (non-finite) with no
  finite `aux` child to anchor its tense -- "He IS running..." has an
  `aux` child tagged `VBZ` (finite), so it stays `complete`; "Running
  quickly down the street." has none. An imperative ("Submit the form.")
  is unaffected: its ROOT is tagged `VB`, not `VBG`, the same base form
  English imperatives always use, so this rule never touches it.
- A lone subordinate clause's own ROOT has a sentence-INITIAL `mark`
  child (the subordinating conjunction itself, "Because"/"Although"/...)
  -- in a real two-clause sentence ("Because X, Y."), spaCy's ROOT is
  always the independent clause's own verb, and the subordinate verb
  (with its `mark` child) sits one level down as an `advcl`, never at
  ROOT -- checked directly on both shapes before trusting this, not
  assumed from one example. A scale-down kept honest, not hidden: the
  `mark` child must be the sentence's very first token for this rule to
  fire, matching the one real failure documented, not every sentence
  that happens to contain a subordinator anywhere.

This module still does not claim to replace a general grammaticality
checker, and is not a grammar or spelling corrector -- a statement
riddled with typos ("i tryed to tork to him") still parses with a verbal
root and is reported `complete`, same scope `spellfix.py`/
`informal_register.py` already own, not duplicated here.
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


_FINITE_TAGS = {"VBZ", "VBD", "VBP", "MD"}


def is_complete_sentence(text: str) -> dict:
    """{"complete": bool, "reason": str, ...}. See module docstring for the
    exact checks and their known blind spots.

    `reason` is one of: "empty", "dangling_<cconj|sconj|adp|det>" (ends on
    a token class that can never legally end a clause), "no_verbal_root"
    (no finite verb anywhere -- a heading/label or a lead-in fragment;
    `heading_like` (token count <= 6) is a weak, token-count-only hint,
    confirmed on EXP-081's real fixture to catch only 1 of 13 genuine
    headings -- treat `no_verbal_root` itself, not `heading_like`, as the
    signal "don't force this into one sentence"), "gerund_fragment" (a
    non-finite `VBG` root with no finite `aux` to anchor it),
    "lone_subordinate_clause" (the root is introduced by a sentence-
    initial subordinating conjunction, with no independent clause), or
    "ok".
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

    root = next((t for t in doc if t.dep_ == "ROOT" and t.pos_ in ("VERB", "AUX")), None)
    if root is None:
        return {"complete": False, "reason": "no_verbal_root", "heading_like": len(tokens) <= 6}

    if root.tag_ == "VBG" and not any(c.dep_ == "aux" and c.tag_ in _FINITE_TAGS for c in root.children):
        return {"complete": False, "reason": "gerund_fragment", "root": root.text}

    mark = next((c for c in root.children if c.dep_ == "mark"), None)
    if mark is not None and mark.i == tokens[0].i:
        return {"complete": False, "reason": "lone_subordinate_clause", "marker": mark.text}

    return {"complete": True, "reason": "ok"}
