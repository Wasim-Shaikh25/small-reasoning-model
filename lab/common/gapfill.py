"""LLM gap-fill: when the deterministic pipeline in brain.py finds nothing
grounded for an ask, ask one of the already-approved bounded rewriter
checkpoints (rewriter_backends.generate) to PROPOSE candidate answer
spans, then validate every proposal independently before accepting any
of them. This is the generic version of what brain.py's timeline path
does today with task-specific glue (entities.DATE_RE + textutil.
sentences) -- instead of writing new deterministic logic per ask type,
the LLM proposes candidates in a fixed schema and the SAME grounding
gate validates every one, for any ask.

No fine-tuning: this is a prompted extraction call on the exact same
bounded checkpoints already permitted for rewriting (FORBIDDEN.md's
bounded-rewriter exception) -- a new USE of an already-approved model,
not a new model.

This module never trusts the LLM's own claim about where a span comes
from or that it quoted correctly. It only trusts lab.common.verify.
quote_check: a candidate is kept only if its span is a verbatim
substring of the exact passage text its own id names. A verbatim
substring cannot contain a number/date/name the source didn't already
contain, so this one check is sufficient grounding for a *span*
proposal (unlike lab.common.proposals.grounding_filter, which has to
check token-by-token because it grounds free-text query proposals,
not verbatim spans). A candidate that fails -- wrong id, paraphrased
instead of quoted, or hallucinated outright -- is dropped silently,
never "corrected": correcting it would mean trusting the LLM's intent,
which is exactly what this gate exists to not do. "NONE" or an empty
candidate list is a valid, honest result (FORBIDDEN.md rule 15, this
project's own no_context_fallback precedent).
"""

from __future__ import annotations

import re

from lab.common.rewriter_backends import generate
from lab.common.verify import quote_check

PROPOSAL_PROMPT = """You are extracting information, not writing new text.
Each answer line has a passage id in brackets, then the shortest exact
phrase copied from that passage -- never a whole sentence if a shorter
exact phrase answers the question, and never copy from a passage that
does not answer the question at all. Do not paraphrase, summarize, or
add anything not written in the passages. If several passages each
answer part of the question, give one line per passage. If nothing in
the passages answers the question, reply with exactly NONE and nothing
else.

Passages:
[x1] The invoice total was $450.00, due on May 2, 2023.
Question: When was the invoice due?
Answer:
[x1] May 2, 2023

Passages:
[x1] The invoice total was $450.00, due on May 2, 2023.
Question: What is the customer's email address?
Answer:
NONE

Passages:
{passage_block}
Question: {ask}
Answer (always start each line with the passage id in brackets, or reply NONE):"""

_LINE_RE = re.compile(r"^\s*\[([^\]]+)\]\s*(.+?)\s*$")


def _build_passage_block(passages: list[dict]) -> str:
    return "\n\n".join(f"[{p['id']}] {p.get('text', '')}" for p in passages)


def _parse_proposals(raw: str) -> list[dict]:
    candidates = []
    for line in (raw or "").splitlines():
        m = _LINE_RE.match(line)
        if m:
            candidates.append({"passage_id": m.group(1).strip(), "span": m.group(2).strip()})
    return candidates


def propose(ask: str, passages: list[dict], checkpoint: str = "gemma3:270m", max_tokens: int = 220) -> list[dict]:
    """Calls the bounded checkpoint once, parses its `[id] text` lines
    into raw (unverified) candidates. Returns `[]` for an empty
    passage list or a "NONE" reply -- never returns anything claiming
    to be grounded; that is validate()'s job, always run after this.
    """
    if not passages:
        return []
    prompt = PROPOSAL_PROMPT.format(ask=ask, passage_block=_build_passage_block(passages))
    raw = generate(checkpoint, prompt, max_tokens)
    return _parse_proposals(raw)


def validate(candidates: list[dict], passages: list[dict]) -> list[dict]:
    """Keeps only candidates whose span is a verbatim substring
    (lab.common.verify.quote_check) of the passage text its own id
    names. Tags every surviving candidate `source: "llm_gapfill"` so
    callers (brain.reason, dependency_tree nodes) can always tell a
    gap-fill-sourced span apart from a deterministically extracted one.
    """
    by_id = {p["id"]: p.get("text", "") for p in passages}
    grounded = []
    for c in candidates:
        passage_text = by_id.get(c["passage_id"])
        if passage_text and quote_check(c["span"], passage_text):
            grounded.append({**c, "source": "llm_gapfill"})
    return grounded


def propose_and_validate(ask: str, passages: list[dict], checkpoint: str = "gemma3:270m", max_tokens: int = 220) -> list[dict]:
    """The one function callers (brain.reason) actually use: propose,
    then validate, in one call -- never expose an unvalidated
    candidate to a caller that might render it.
    """
    return validate(propose(ask, passages, checkpoint, max_tokens), passages)
