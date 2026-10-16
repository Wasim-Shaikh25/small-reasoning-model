"""The no-context fallback: FORBIDDEN.md's narrow exception recorded 2026-10-16.

Answers from the bounded checkpoint's own pretrained knowledge, but only
when lab.common.brain.reason is called with literally no passages at all --
never when retrieval ran and came up empty, which stays the existing
abstain path (ABSTAIN_TEXT), completely unchanged. That distinction is
enforced at the call site (lab.common.brain.reason checks `not passages`
before anything else runs), not here; this module has no way to tell the
two cases apart on its own and must never be called for the second one.

decision is always "ungrounded", never "supported" -- downstream code must
never attribute this text as evidence or a citable finding. The one
structural safety check possible here, with no source to check faithfulness
against: the output must not contain a citation marker (`[...]`) at all. A
bracketed marker in an ungrounded answer would be fabricated, not real, and
is rejected outright rather than shown, same as a fidelity failure falls
back to a safe default elsewhere in this repo.
"""

from __future__ import annotations

from lab.common.prompt_contract import build as build_prompt
from lab.common.verify import citation_markers

ROLE_INSTRUCTION = (
    "Answer the question directly and concisely from your own general knowledge. "
    "You have not been given any source text or passages to work from -- there is "
    "nothing to quote or cite. Do not write a citation marker in square brackets; "
    "there is nothing to put inside one."
)
OUTPUT_FORMAT = "A short, direct answer in plain prose. No citation markers, no bracketed references."
DISCLAIMER = "[Not grounded in any provided evidence -- general knowledge only.] "


def _generate(ask: str, max_tokens: int) -> str:
    from lab.common.real_rewriter_ollama import generate as generate_ollama

    prompt = build_prompt(ROLE_INSTRUCTION, data=None, output_format=OUTPUT_FORMAT, labeled=True)
    prompt = f"{prompt}\n\nQUESTION: {ask.strip()}"
    return generate_ollama(prompt, max_tokens=max_tokens)


def answer_from_general_knowledge(ask: str, max_tokens: int = 160) -> dict:
    generated = _generate(ask, max_tokens)
    markers = citation_markers(generated)
    if markers:
        return {
            "decision": "ungrounded",
            "text": "Insufficient evidence.",
            "used_generative": False,
            "fallback_reason": "fabricated_citation_marker",
            "generated_text": generated,
        }
    return {
        "decision": "ungrounded",
        "text": DISCLAIMER + generated.strip(),
        "used_generative": True,
        "fallback_reason": None,
        "generated_text": generated,
    }
