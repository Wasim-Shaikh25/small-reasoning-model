"""Bounded FLAN-T5 rewriter: joins already-verified findings into prose, fidelity-gated.

This is the narrow exception recorded in FORBIDDEN.md on 2026-10-14. It is the
only place in this repository that loads a generative language model, and it
is never given raw passages, a question, or a support/contradiction judgment
to make -- only a batch of findings that the lexical QA extractor and the
lexical NLI judge have already verified, plus a style instruction. Every
output is checked by `fidelity_gate` before use; a failure discards the
generated text and falls back to `assemble.render_unit`'s deterministic
output, never a partial accept.
"""

from __future__ import annotations

import re

from lab.common.assemble import render_unit
from lab.common.prompt_contract import build as build_prompt_contract
from lab.common.relevance import ask_relevance
from lab.common.verify import bidirectional_nli, citation_markers, entity_number_check, modality_preserved, strip_citation_markers

MODEL_NAME = "google/flan-t5-small"

_tokenizer = None
_model = None


def load():
    global _tokenizer, _model
    if _tokenizer is None or _model is None:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
        _model.eval()
    return _tokenizer, _model


def model_card() -> dict:
    return {
        "checkpoint": MODEL_NAME,
        "params_approx": "~77M",
        "role": "rewriter only (ARCHITECTURE.md section 3.7): join verified findings into prose",
        "source": f"https://huggingface.co/{MODEL_NAME}",
        "not_used_for": ["extraction", "answering", "support/contradiction judging", "proposing"],
        "forbidden_reference": "FORBIDDEN.md, 'bounded rewriter exception', recorded 2026-10-14",
    }


def _source_lines(leaf: dict, glossary: dict[str, str]) -> tuple[list[str], list[str]]:
    lines = []
    cite_ids = []
    for finding in leaf["findings"]:
        statement = finding["statement"]
        for variant, canonical in glossary.items():
            statement = re.sub(rf"\b{re.escape(variant)}\b", canonical, statement)
        cite = finding.get("citation") or finding.get("evidence_id")
        lines.append(f"{statement} [{cite}]")
        cite_ids.append(cite)
    return lines, cite_ids


def build_prompt(leaf: dict, glossary: dict[str, str], ask: str | None = None) -> tuple[str, str, list[str]]:
    lines, cite_ids = _source_lines(leaf, glossary)
    src_text = "\n".join(lines)
    instruction = (
        "Rewrite the single verified fact below as one grammatically correct sentence. "
        "Do not remove it, shorten it, or leave it blank. Do not add any fact, name, number, "
        "or date not listed below. Keep the citation marker exactly as written, in square "
        "brackets."
        if len(leaf["findings"]) == 1
        else "Combine these verified facts into one flowing paragraph. Do not drop any of them. "
        "Do not add any fact, name, number, or date not listed below. Keep every citation "
        "marker exactly as written, in square brackets."
    )
    if ask:
        instruction += f" This is for answering: {ask.strip()}"
    # lab.common.prompt_contract, labeled=False: byte-identical to the
    # pre-contract "instruction + blank line + src_text" every fidelity
    # measurement since EXP-048 was taken against -- the mandatory prompt
    # format (EXP-072) wraps this call site rather than changing its text.
    prompt = build_prompt_contract(instruction, src_text, labeled=False)
    return prompt, src_text, cite_ids


def fidelity_gate(src_text: str, out_text: str, cite_ids: list[str], ask: str | None = None) -> dict:
    """ARCHITECTURE.md section 3.7's fidelity validator, applied to a rewrite candidate.

    Checks faithfulness to the source findings (numbers, modals, bidirectional
    entailment, citations) and, when an `ask` is supplied, also checks the
    output didn't drift away from what was actually asked (lab.common.relevance).
    A rewrite can stay perfectly faithful to its source and still be useless if
    it no longer serves the ask -- these are two different failure modes, not
    one.
    """
    # Citation markers contain digits too ("[5]"), and lab.common.textutil.
    # numbers() has no way to tell a citation id from a real quantity -- so
    # comparing the two texts unmodified double-counts one dropped citation
    # as both a "citations" failure and a "numbers" failure (found while
    # investigating why Qwen2.5-0.5B-Instruct's otherwise-faithful rewrites
    # were scored as having dropped numbers that were never really content
    # numbers at all, only citation ids). Stripping markers before this one
    # check keeps it about actual quantities; the citation check below
    # still runs on the unmodified text, where the markers belong.
    numbers = entity_number_check(strip_citation_markers(src_text), strip_citation_markers(out_text))
    modal_ok = modality_preserved(src_text, out_text)
    nli = bidirectional_nli(src_text, out_text)
    found_markers = set(citation_markers(out_text))
    missing_citations = sorted(set(cite_ids) - found_markers)
    broken_citations = sorted(found_markers - set(cite_ids))
    relevance = ask_relevance(ask, out_text) if ask else None
    reasons = []
    if not numbers["ok"]:
        reasons.append("numbers")
    if not modal_ok:
        reasons.append("modal")
    if not nli["ok"]:
        reasons.append("nli")
    if missing_citations or broken_citations:
        reasons.append("citations")
    if relevance is not None and not relevance["relevant"]:
        reasons.append("ask_relevance")
    return {
        "ok": not reasons,
        "numbers": numbers,
        "modal_preserved": modal_ok,
        "nli": nli,
        "missing_citations": missing_citations,
        "broken_citations": broken_citations,
        "ask_relevance": relevance,
        "fail_reasons": reasons,
    }


def _generate(tok, mdl, prompt: str, max_new_tokens: int) -> str:
    import torch

    with torch.no_grad():
        inputs = tok(prompt, return_tensors="pt", truncation=True, max_length=512)
        out_ids = mdl.generate(**inputs, max_new_tokens=max_new_tokens, num_beams=4)
    return tok.decode(out_ids[0], skip_special_tokens=True).strip()


def _missing_feedback(checks: dict) -> str | None:
    """Name exactly what the previous attempt dropped, for the retry prompt.

    This is a control mechanism, not a hope: instead of asking the model to
    try harder in general, it is told precisely which tokens its own last
    output was missing. If that is enough to fix it, the model could hold
    the fact all along and simply was not told clearly enough what it
    missed -- a different finding than "it structurally cannot."
    """
    missing = []
    if checks["numbers"]["numbers_dropped"]:
        missing.extend(checks["numbers"]["numbers_dropped"])
    missing.extend(checks["missing_citations"])
    if not missing:
        return None
    return f"Your previous attempt was missing: {', '.join(missing)}. Rewrite again and include all of them."


def rewrite_unit(
    leaf: dict,
    glossary: dict[str, str],
    tokenizer=None,
    model=None,
    max_new_tokens: int = 160,
    ask: str | None = None,
    max_retries: int = 0,
) -> dict:
    """Generative counterpart to `assemble.render_unit`. Same input shape, fidelity-gated.

    Returns {"text", "used_generative", "generated_text", "checks", "fallback_reason",
    "attempts"}. `text` is the generated prose when it passes the gate, otherwise the
    unchanged deterministic output -- never a partial accept of a failing rewrite.
    `ask`, when supplied, is also checked for relevance (see `fidelity_gate`).

    `max_retries` (default 0, so existing callers are unaffected): on a failed
    attempt, instead of falling back immediately, tell the model exactly what
    its own output dropped (`_missing_feedback`) and regenerate, up to this
    many additional attempts, before falling back to the deterministic text.
    """
    deterministic_text = render_unit(leaf, glossary)
    prompt, src_text, cite_ids = build_prompt(leaf, glossary, ask=ask)
    tok, mdl = (tokenizer, model) if tokenizer is not None and model is not None else load()

    attempts = []
    current_prompt = prompt
    for attempt_num in range(max_retries + 1):
        generated = _generate(tok, mdl, current_prompt, max_new_tokens)
        checks = fidelity_gate(src_text, generated, cite_ids, ask=ask)
        attempts.append({"attempt": attempt_num, "prompt": current_prompt, "generated": generated, "ok": checks["ok"], "fail_reasons": checks["fail_reasons"]})
        if checks["ok"]:
            return {
                "text": generated,
                "used_generative": True,
                "generated_text": generated,
                "checks": checks,
                "fallback_reason": None,
                "attempts": attempts,
            }
        feedback = _missing_feedback(checks)
        if feedback is None or attempt_num == max_retries:
            break
        current_prompt = f"{prompt}\n\n{feedback}"

    return {
        "text": deterministic_text,
        "used_generative": False,
        "generated_text": attempts[-1]["generated"],
        "checks": checks,
        "fallback_reason": checks["fail_reasons"],
        "attempts": attempts,
    }
